# Step 1 — Source normalization and the reported bug

Fixes issue #297 as reported. Establishes the forward-slash invariant at its two
enforcement points and removes the two workarounds that become dead.

## WHERE

| File | Role |
|---|---|
| `src/mcp_workspace/file_tools/directory_utils.py` | `_discover_files` — enforcement point for all listing/search output |
| `src/mcp_workspace/file_tools/path_utils.py` | `normalize_path` — enforcement point for anything derived from a validated path |
| `src/mcp_workspace/file_tools/tree_listing.py` | `list_directory_tree` — normalize `base_path` |
| `src/mcp_workspace/file_tools/search.py` | `_norm` — remove the dead workaround |
| `tests/file_tools/test_tree_listing.py` | regression guard (new test) |
| `tests/file_tools/test_directory_utils.py` | new invariant assertion; fix two existing assertions |
| `tests/file_tools/test_path_utils.py` | new exact-string test; fix two existing assertions |
| `tests/file_tools/test_search.py` | drop `_discover_files` mocks that existed only to dodge separators |
| `tests/test_server.py` | tighten the near-miss integration assertion |

## WHAT

No signature changes. Four bodies change.

```python
# directory_utils.py — _discover_files(directory: Path, project_dir: Path) -> List[str]
rel_file_path = rel_root.joinpath(file).as_posix()   # was: str(rel_root / file)

# path_utils.py — normalize_path(path: str, project_dir: Path) -> tuple[Path, str]
return joined_path, relative_path.as_posix()          # was: str(relative_path)

# tree_listing.py — list_directory_tree(file_paths, base_path=".", dirs_only=False) -> List[str]
base_path = base_path.replace("\\", "/")              # new, first line after the empty guard

# search.py — _norm(p: str) -> str
slashed = p                                            # was: p.replace("\\", "/")
```

## HOW

- `rel_root.joinpath(file)` rather than `rel_root / file` so the `as_posix()` call reads as
  one expression. Behaviour at the project root is unchanged: `Path(".").joinpath("f")` is
  `Path("f")`, whose `as_posix()` is `"f"` — the same bare filename produced today.
- `normalize_path`'s **absolute** return value is untouched. Only the relative half of the
  tuple changes. The `_outside_error` messages keep native separators; that is the stated
  boundary.
- `list_directory_tree` normalizes `base_path` once, before it feeds both `_build_tree`
  (where it becomes `strip_prefix`) and `render_prefix`. `_build_tree` **keeps** its
  existing per-path `replace("\\", "/")` — see the deviation note in `summary.md` for why
  removing it would break the regression test rather than fix it.
- `search._norm` keeps the win32 `.lower()`; only the `replace` goes. The `.lower()` is
  deliberate case-insensitive globbing, pinned by `test_windows_case_insensitive_match_preserved`.
  After the change `_norm` may collapse to a single expression — keep the function, it is
  the documented normalization hook.
- No new imports anywhere. No `logging` import is added to `tree_listing.py`.

## ALGORITHM

`list_directory`'s path through the fixed code, scoped to `docs/architecture`:

```
_discover_files walks the subtree, emits "docs/architecture/architecture.md"  (as_posix)
normalize_path("docs/architecture") returns rel = "docs/architecture"          (as_posix)
list_directory_tree normalizes base_path (no-op here, load-bearing on Windows)
_build_tree strips "docs/architecture/" -> tree holds "architecture.md"
_render re-adds render_prefix "docs/architecture/" -> "docs/architecture/architecture.md"
```

The strip-then-re-add is kept: collapse depth is measured from the scope root, and
`_find_collapsible` only considers `depth >= 2`.

## DATA

- `_discover_files` → `List[str]`, every entry forward-slash separated, project-relative.
- `normalize_path` → `tuple[Path, str]`; the `Path` is unchanged and still native, the
  `str` is now forward-slash separated.
- `list_directory_tree` → `List[str]`; file entries are now valid paths accepted by
  `read_file`. Collapsed lines (`dir/ (N files)`), the truncation summary and
  `dirs_only=True` entries keep their existing shapes.

## Tests (write first)

New:

1. `test_tree_listing.py` — feed `list_directory_tree` explicitly backslash-separated
   paths **and** a backslash `base_path`; assert the exact expected forward-slash output.
   This is the real regression guard and it fails on any platform.
2. `test_directory_utils.py` — assert `_discover_files` output itself contains no `"\\"`.
   Both existing tests normalize both sides, so nothing asserts this today.
3. `test_path_utils.py` — assert `normalize_path` returns the exact string
   `"a/b/c.txt"` for a nested path, with neither side round-tripped through `Path`.
4. `test_server.py` — integration: a small, non-collapsed, non-truncated scoped
   `list_directory` whose file entries are accepted by `read_file` unmodified. Assert each
   path appears exactly once. Cover project root, one level deep, nested, a directory with
   subdirectories, and `dirs_only=True`.

Modified:

5. `test_directory_utils.py:78` and `:85` (`test_git_directory_exclusion`) — normalize both
   sides. `:85` in particular starts passing for the wrong reason otherwise: the expected
   backslash string becomes unproducible, so it silently stops guarding `.git` exclusion.
6. `test_path_utils.py:78` and `:94` — these compare against `str(TEST_DIR / ...)`, which is
   backslash-separated on win32.
7. `test_server.py::test_list_directory_path_subtree_integration` — the near-miss. It
   asserts `any("a.py" in entry ...)`, which the duplicated prefix satisfies. Tighten to
   exact equality.
8. `test_search.py` — drop the `_discover_files` mocks that existed only to dodge
   separators. Leave any mock that is load-bearing for another reason.

Existing `test_search.py` assertions use `Path(m["file"]).name`, `endswith`, or bare names,
so the `search_files` output switch to `/` is low-risk. A sweep of `tests/` for assertions
matching message text containing a path found none.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with `["-n", "auto"]`,
`run_mypy_check`. One commit.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`, then implement step 1.
>
> This is the commit that fixes issue #297: `list_directory` duplicates the scope prefix on
> Windows because `_build_tree` compares a forward-slashed path against a backslashed
> `base_path`.
>
> Work test-first. Write the four new tests and the four test fixes listed under **Tests**
> before touching `src/`, confirm the new regression guard in `test_tree_listing.py` fails,
> then make the four source changes in **WHAT**.
>
> Note the deliberate deviation from the issue text, explained in `summary.md`: normalize
> `base_path` in `list_directory_tree` and **keep** `_build_tree`'s per-path
> `replace("\\", "/")`. Do **not** remove it and do **not** add a `logging` import or an
> unmatched-prefix warning to `tree_listing.py` — the issue's version of that change leaves
> the reported bug unfixed for backslash input.
>
> Do not touch `checks/file_sizes.py`, `delete_directory`, `_check_not_gitignored`, or any
> docstring or doc file — those are steps 2, 3 and 5.
>
> Use the MCP tools per `CLAUDE.md`. Run `run_format_code`, then `run_pylint_check`,
> `run_pytest_check` with `extra_args: ["-n", "auto"]`, and `run_mypy_check`. All must pass.
> Commit once.
