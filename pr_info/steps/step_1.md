# Step 1 — Unify and harden `normalize_path`

Read [summary.md](./summary.md) first, especially "Traps to carry through every step".

This is the vulnerability itself. Steps 2–4 are what it exposes and what it needs proving.

## WHERE

| File | Change |
|---|---|
| `tests/conftest.py` | Add a shared `requires_symlinks` skip marker |
| `tests/file_tools/test_path_utils.py` | Add 2 fixtures + 4 parametrized tests; leave the 6 existing tests byte-identical |
| `src/mcp_workspace/file_tools/path_utils.py` | Rewrite `normalize_path`, add `_outside_error`, remove `import os` |

## WHAT

```python
# tests/conftest.py
def _symlinks_supported() -> bool: ...
requires_symlinks = pytest.mark.skipif(
    not _symlinks_supported(),
    reason="symlink creation not permitted on this platform",
)

# src/mcp_workspace/file_tools/path_utils.py
def _outside_error(path: str, project_dir: Path, reason: str) -> ValueError: ...
def normalize_path(path: str, project_dir: Path) -> tuple[Path, str]: ...   # signature unchanged
```

## HOW

- `_outside_error` is module-private, returns (does not raise) the `ValueError`, and is used
  at all three raise sites so every message carries both `"traversal"` and
  `"outside the project directory"` by construction.
- `import os` is removed — `os.path.commonpath` at `path_utils.py:61` was its only use.
  `Path.is_relative_to` replaces it (Python 3.9+; this project is 3.11+).
- `requires_symlinks` lives in `tests/conftest.py` rather than being re-implemented inline
  the way `test_move_operations.py:317` does it, because step 1 needs it in several places.
  Import it in the test module as `from tests.conftest import requires_symlinks`
  (`test_path_utils.py:11` already imports `TEST_DIR` from there).
- No caller changes. No signature changes.

## ALGORITHM

`_symlinks_supported`, evaluated once at conftest import:

```
with tempfile.TemporaryDirectory() as tmp:
    target = Path(tmp)/"target"; target.touch()
    try: (Path(tmp)/"link").symlink_to(target)
    except (OSError, NotImplementedError): return False
return True
```

`normalize_path`:

```
if project_dir is None: raise ValueError("Project directory cannot be None")
path_obj = Path(path)
joined = path_obj if path_obj.is_absolute() else project_dir / path_obj
if ".." in joined.parts:
    raise _outside_error(path, project_dir, "contains '..' traversal and would escape")
try:                                    # both resolve() calls inside ONE try
    if not joined.resolve().is_relative_to(project_dir.resolve()):
        raise _outside_error(path, project_dir, "resolves to a location")
except OSError:                         # resolve() unavailable; the '..' guard already ran
    logger.warning("Path.resolve() failed for '%s', using fallback check", joined)
try: rel = joined.relative_to(project_dir)
except ValueError as exc: raise _outside_error(path, project_dir, "is") from exc
return joined, str(rel)
```

The `except OSError` handler needs **no** body beyond the warning: the `..` guard above and
the wrapped `relative_to` below carry the validation between them. Adding a second
`".." in parts` check there would be dead code.

## DATA

`_outside_error` message template — the one shape that satisfies all seven asserting tests:

```
f"Security error: Path '{path}' {reason} outside the project directory "
f"'{project_dir}'. Path traversal is not allowed."
```

`normalize_path` returns `tuple[Path, str]`, unchanged in shape:

| Element | Value | Invariant |
|---|---|---|
| `abs_path` | the **lexically joined** path — names the symlink, not its target | never resolved |
| `rel_path` | `str(joined.relative_to(project_dir))` | never contains `..`, by construction |

Update the docstring on two axes:

- **Design** — resolution is used to *validate* while the *joined* path is returned, and why
  (symlink semantics + the three `relative_to` call sites).
- **Contract** — the `Raises:` section must name both newly rejected input classes, not just
  "outside the project directory": a `..` segment **anywhere** in the path, including
  mid-path (`src/../README.md`), and a path that resolves outside the project through a
  symlink — an in-project symlinked file, or an intermediate symlinked directory component,
  neither of which contains `..`. This docstring is the in-code home of the behaviour change;
  `README.md` (step 5) is the user-facing one.

`_outside_error` needs a docstring with a `Returns:` section — it returns the `ValueError`
rather than raising it, and ruff's DOC201 applies to `path_utils.py` (it is not in the
`DOC502` per-file ignore list in `pyproject.toml`).

## Tests (write first)

Two fixtures in `test_path_utils.py`:

```python
@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    """project/ and a sibling outside/ holding credentials.env."""
    # project (resolved — the server resolves --project-dir at startup), outside/credentials.env,
    # project/inside.txt

@pytest.fixture
def link_layout(layout: dict[str, Path]) -> dict[str, Path]:
    """layout plus project/link.env -> outside/credentials.env, project/link -> outside,
    project/inside_link.txt -> project/inside.txt."""
```

Four tests, all built from `tmp_path` so the absolute branch is exercised on Windows too:

1. `test_normalize_path_rejects_traversal` — parametrized over the payloads below, each
   asserting `ValueError` whose message contains `"Security error"` **and**
   `"outside the project directory"`:
   - absolute `..`: `str(project / ".." / "outside" / "credentials.env")` (the defect)
   - relative `..`: `"../outside/credentials.env"` (the control — already rejected today)
   - mid-path `..`: `"src/../README.md"` (newly rejected; acceptance criterion)
2. `test_normalize_path_rejects_symlink_escape` — `@requires_symlinks`, parametrized over
   four forms: `"link.env"`, `str(project / "link.env")`, `"link/credentials.env"`,
   `str(project / "link" / "credentials.env")`. The last two are the intermediate
   symlinked-directory shape.
3. `test_normalize_path_accepts_in_project` — parametrized over `"inside.txt"` and
   `str(project / "inside.txt")`; asserts `abs_path == project / "inside.txt"`,
   `rel_path == "inside.txt"`, and `".." not in Path(rel_path).parts` (the post-condition
   guarding guard 1).
4. `test_normalize_path_accepts_internal_symlink` — `@requires_symlinks`; a symlink that
   stays inside the project is allowed, and `abs_path.is_symlink()` is `True` — the returned
   path is the link, not its target.

Do not touch the 6 existing tests. `test_normalize_path_oserror_with_traversal_rejected`
stops exercising the `OSError` fallback (the `..` guard intercepts its input first) but
still passes; that is expected and is not to be "fixed" by reordering the guards.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`, plus `run_ruff_check` and `run_vulture_check`.

Ruff is configured with `select = ["D", "DOC"]` (`pyproject.toml`), so it checks docstrings
only and will *not* flag the removed `import os` — it is here for the rewritten docstrings,
and it requires a `Returns:` section on `_outside_error` (DOC201). `run_vulture_check` is the
one that speaks to dead code after the import removal.

## Commit

`fix(path_utils): validate absolute paths against the resolved path (#290)`

## LLM prompt

> Implement step 1 of the plan in `pr_info/steps/step_1.md`, using `pr_info/steps/summary.md`
> for context (read both in full before starting, including the summary's "Traps" section).
>
> Work TDD: add `requires_symlinks` to `tests/conftest.py` and the two fixtures plus four
> parametrized tests to `tests/file_tools/test_path_utils.py` first, watch them fail, then
> rewrite `normalize_path` in `src/mcp_workspace/file_tools/path_utils.py` per the ALGORITHM
> section and remove the now-unused `import os`.
>
> Hard constraints: the six existing tests in `test_path_utils.py` must pass **unchanged**;
> the returned `abs_path` is the lexically joined path, never the resolved one; both
> `resolve()` calls sit inside one `try`; the `OSError` handler gets no `..` check of its own;
> every error message must contain both `"traversal"` and `"outside the project directory"`.
> Build every test path from `tmp_path` — a hardcoded `/tmp/...` string is not absolute on
> Windows and would silently test the wrong branch.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check`, `run_ruff_check` and `run_vulture_check`.
> Report the symlink tests' skip status explicitly — on Windows without symlink privileges
> they skip, which means variant 2 is unverified locally and only CI proves it.
>
> One commit for the step. Do not start step 2.
