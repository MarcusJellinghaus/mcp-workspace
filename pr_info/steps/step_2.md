# Step 2 — `search_files` skips a rejected file and reports it

Read [summary.md](./summary.md) first. Depends on step 1.

`_search_content` calls `normalize_path` on every file the directory walk produced, at
`search.py:97`, **outside** the `try` at `:98-102` — which wraps only `open`/`readlines` and
catches only `UnicodeDecodeError`. Today that call cannot fail. After step 1 a single
non-gitignored symlink pointing outside the project aborts the entire `search_files` call:
one file taking out one tool repo-wide. The fix is to skip the file and say so.

The affected set is narrow. `search_files` calls `list_files(".", use_gitignore=True)`
(`search.py:191`), so `.venv` and friends never reach the walk, and `_discover_files` walks
with `os.walk` at default `followlinks=False` (`directory_utils.py:63`), appending only
entries from `files` — so a symlinked *directory* neither is descended into nor contributes
files. Only a symlinked file entry can surface.

## WHERE

| File | Change |
|---|---|
| `tests/file_tools/test_search.py` | Add 3 tests (one `@requires_symlinks`) |
| `src/mcp_workspace/file_tools/search.py` | `_search_content`: move the `normalize_path` call inside the `try`, add a handler, add the result key; document the key |
| `src/mcp_workspace/server.py` | One docstring line in the `search_files` MCP tool |
| `src/mcp_workspace/server_reference_tools.py` | One docstring line in `search_reference_files` |

## WHAT

No signature changes. `_search_content` and `search_files` keep their current signatures; the
returned dict gains one optional key.

## HOW

- Report under `skipped_files`, present **only when non-empty** — the same pattern
  `glob_note` and `note` already follow (`search.py:194, 217-220`). Silence is the failure
  mode `glob_note` exists to prevent: a file quietly missing from results is
  indistinguishable from a genuine absence.
- Widen the handler to `OSError` as well as `ValueError`. A broken symlink or an unreadable
  file already aborts a whole search today; catching the new `ValueError` while leaving
  `OSError` to abort would be incoherent.
- Glob-only mode never calls `normalize_path`, so `skipped_files` appears in content-search
  results only. That is correct, not an omission.
- Document the key in all three docstrings. Two are the user-visible MCP tool descriptions
  (`server.py`, `server_reference_tools.py`); the third is the utility others read.

## ALGORITHM

Inside `_search_content`, replacing lines 96–102:

```
skipped: List[str] = []
for rel_path in files:
    try:
        abs_path, _ = normalize_path(rel_path, project_dir)
        with open(abs_path, "r", encoding="utf-8") as f:
            file_lines = f.readlines()
    except UnicodeDecodeError:          # MUST precede the next handler — it is a ValueError subclass
        continue                        # binary files stay a silent skip (test_search.py:427)
    except (ValueError, OSError):
        skipped.append(rel_path)
        continue
    ...unchanged match loop...
```

and, after the `result` dict is built:

```
if skipped:
    result["skipped_files"] = skipped
```

## DATA

`skipped_files: List[str]` — project-relative paths, in walk order, exactly as
`_discover_files` reported them. Absent when nothing was skipped.

Reported match paths do not shift: `search.py` discards `normalize_path`'s relative return
(`abs_path, _ = ...`) and reports the walk's own path.

Docstring line (all three places, adapted to local wording):

> Carries a `skipped_files` key listing project-relative paths that could not be read —
> a path rejected by the security check, or an unreadable file — present only when non-empty.

## Tests (write first)

1. `test_search_reports_skipped_file` — parametrized over
   `[ValueError("Security error: ..."), OSError("boom")]`. Write two matching files, then
   `monkeypatch.setattr` `mcp_workspace.file_tools.search.normalize_path` to a wrapper that
   raises the parametrized exception for one filename and delegates to the real function
   otherwise. Assert the search still returns, the good file is in `details`, the bad file is
   not, and `result["skipped_files"] == ["bad.py"]`. Runs on every platform — no symlink
   privilege needed.
2. `test_binary_file_not_reported_as_skipped` — a binary file plus a matching text file, no
   patching; assert `"skipped_files" not in result`. This pins the handler ordering directly:
   drop the `UnicodeDecodeError` handler or put it second and this test fails.
3. `test_search_skips_real_symlink_escape` — `@requires_symlinks` (step 1's shared marker,
   `from tests.conftest import requires_symlinks`), no patching at all. Create
   `outside/credentials.env` as a sibling of `project_dir`, a matching in-project file, and
   a non-gitignored `project_dir/link.env -> outside/credentials.env`; both files contain the
   search pattern. Assert the call returns, the in-project file is in `details`, the target's
   content is not, and `result["skipped_files"] == ["link.env"]`.

   This is the only test that proves the real failure mode end to end: the other two reach the
   handler through a patched `normalize_path`, so they cannot check that a symlinked file
   actually reaches `_search_content` — the claim the "affected set is narrow" reasoning above
   rests on. Skips on Windows without symlink privileges; `ubuntu-latest` CI proves it.

`test_search_files_skips_binary_files` (`test_search.py:427`) must pass unchanged.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`.

## Commit

`fix(search): skip and report files rejected by the path guard (#290)`

## LLM prompt

> Implement step 2 of the plan in `pr_info/steps/step_2.md`, using `pr_info/steps/summary.md`
> for context. Step 1 must already be committed.
>
> Work TDD: add the three tests to `tests/file_tools/test_search.py` first, then change
> `_search_content` in `src/mcp_workspace/file_tools/search.py` per the ALGORITHM section,
> then add the one-line `skipped_files` note to the three docstrings listed under WHERE.
>
> The one trap: `UnicodeDecodeError` is a subclass of `ValueError`, so its handler must stay
> separate and come first — otherwise binary files land in `skipped_files` and
> `test_search_files_skips_binary_files` at `test_search.py:427` fails. Set `skipped_files`
> only when the list is non-empty, matching how `glob_note` is set.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, and `run_mypy_check`. One commit for the step.
