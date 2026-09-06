# Summary — Issue #290: `normalize_path()` absolute branch never resolves

## Problem

`normalize_path()` (`src/mcp_workspace/file_tools/path_utils.py`) has two branches. The
absolute branch validates with the purely lexical `Path.relative_to()` and never calls
`.resolve()`, so an absolute path that merely *starts* with the project directory passes
even when it leaves it. Two variants escape confinement:

1. `..` in an absolute path — `<project>/../outside/credentials.env`.
2. An in-project symlink pointing outside — a symlinked **file**, or an intermediate
   symlinked **directory** component (`<project>/link/evil.txt`). Contains no `..`.

`normalize_path` is the single chokepoint for every file operation (read, write, edit,
delete, move, list, search) with no second guard downstream, and reference-project tools
pass their own path in as `project_dir`, so they inherit the defect identically.

CWE-22, CVSS 8.4. Affects `<= 0.1.12`.

## Fix

Collapse the two branches into one, guard twice, and keep the return contract byte-identical:

- Anchor relative input to the project directory (`project_dir / path_obj`); leave absolute
  input as-is. One set of checks runs over the result.
- **Guard 1** — reject `..` anywhere in `joined_path.parts`. Closes variant 1 and makes the
  `..`-free invariant true by construction.
- **Guard 2** — validate containment against `joined_path.resolve()` vs
  `project_dir.resolve()`. Closes variant 2, which contains no `..` to reject.
- **Return the lexically-joined path**, not the resolved one, so `delete_this_file` unlinks
  the link rather than its target, `move_file` relocates the link, and the three call sites
  that do `relative_to(project_dir)` on the returned path keep working.

## Architectural / design changes

| Change | Rationale |
|---|---|
| Two branches become one linear body | Patching only the absolute branch would duplicate the containment logic in two places. The unified function is *shorter* than today's — the nested `try` and the `if "Security error:" in str(e)` message-sniffing re-wrap both disappear (~50 lines to ~25). |
| Validation path and return path deliberately differ | Resolve to *decide*; return the joined path. This is the single design decision the whole fix hangs on, and it is what keeps symlink semantics (link, not target) and the three downstream `relative_to` call sites intact. Documented in the function docstring. |
| One error-message helper, three call sites | Seven existing tests assert on message substrings, and the `..` message must carry **both** `"traversal"` and `"outside the project directory"` because the `..` guard now runs first and intercepts inputs that previously hit the containment branch. A helper makes that coexistence structural rather than a coincidence to be maintained by vigilance. |
| `os.path.commonpath` → `Path.is_relative_to` | Clarity, not a bug fix. `commonpath` was the sole use of `os` in the module, so `import os` goes. Both fail closed on cross-drive paths. |
| `search_files` gains a per-file failure mode | `_search_content` calls `normalize_path` on every walked file. After the fix one rejected file would abort the whole search — a repo-wide outage of one tool caused by one file. It now skips the file and reports it under `skipped_files`, following the existing `glob_note` precedent: neither silent nor fatal. |
| Reference-project tools change not at all | They already funnel through the same chokepoint with an already-resolved `project_dir`. They inherit the fix; the change is one regression test that says so out loud. |

### Deliberately not changed

- **Not returning the resolved path.** It would make `delete_this_file` unlink a symlink's
  target and `move_file` leave a dangling link, and would silently break
  `file_operations.py:458`, `directory_utils.py:69` and `git_operations/core.py:117`.
- **Not hardening `set_project_dir`** — out of scope; the resolved-vs-raw mixing never
  arises once the return contract is unchanged.
- **Not touching `server.py:280`'s fail-open gitignore check** — pre-existing, unaffected,
  worth its own issue.
- **TOCTOU** — resolve-then-open is inherently racy. Out of scope: the confined party is the
  MCP client, which has no symlink-creation primitive through this server.

## Breaking changes

Both are intentional and narrow:

1. An in-project symlink pointing **outside** the project is now rejected. A repo with a
   tracked, non-ignored symlink to a shared file outside the checkout loses access to it.
2. A mid-path `..` is now rejected — `read_file("src/../README.md")` starts failing. No
   existing test depends on it.

Both are stated in `README.md` by step 5. This repo has no `CHANGELOG.md` or release-notes
file, and the issue's Decisions table puts release logistics (GHSA publication, crediting the
five reporters, the release itself) outside this issue, so the README is the user-visible
surface this plan writes to. The advisory text and reporter credits stay out of it.

## Files created / modified

| Path | Step | Change |
|---|---|---|
| `src/mcp_workspace/file_tools/path_utils.py` | 1 | **Modified** — unified `normalize_path`, new `_outside_error` helper, `import os` removed |
| `tests/conftest.py` | 1 | **Modified** — shared `requires_symlinks` skip marker |
| `tests/file_tools/test_path_utils.py` | 1 | **Modified** — layout fixtures + 4 parametrized tests; 6 existing tests untouched |
| `src/mcp_workspace/file_tools/search.py` | 2 | **Modified** — `_search_content` skips and reports rejected files |
| `src/mcp_workspace/server.py` | 2 | **Modified** — one docstring line (`skipped_files`) |
| `src/mcp_workspace/server_reference_tools.py` | 2 | **Modified** — one docstring line (`skipped_files`) |
| `tests/file_tools/test_search.py` | 2 | **Modified** — 3 tests added (one `@requires_symlinks`) |
| `tests/file_tools/test_file_operations.py` | 3 | **Modified** — 1 parametrized operation-level test |
| `tests/test_reference_projects_mcp_tools.py` | 4 | **Modified** — 1 async test |
| `README.md` | 5 | **Modified** — `## Path Confinement` section + 1 Security Notes bullet |

No new modules, packages or folders. No public signature changes.

## Steps

| Step | Scope | Commit |
|---|---|---|
| [step_1.md](./step_1.md) | The vulnerability: unify and harden `normalize_path`, with regression tests for both variants | `fix(path_utils): validate absolute paths against the resolved path (#290)` |
| [step_2.md](./step_2.md) | `search_files` survives a rejected file and reports it as `skipped_files` | `fix(search): skip and report files rejected by the path guard (#290)` |
| [step_3.md](./step_3.md) | Operation-level absolute-traversal coverage | `test(file_operations): cover absolute-path traversal (#290)` |
| [step_4.md](./step_4.md) | Reference-project traversal coverage | `test(reference): cover absolute-path traversal (#290)` |
| [step_5.md](./step_5.md) | README states the two newly rejected input classes | `docs(readme): state the two paths the guard now rejects (#290)` |

Steps are independently committable and ordered by dependency. Step 1 alone leaves the suite
green — no existing test plants a symlink pointing outside the project — so step 2 is a
resilience fix, not a repair of step 1.

## Traps to carry through every step

- **`UnicodeDecodeError` is a subclass of `ValueError`.** In `_search_content` the Unicode
  handler must stay separate and come **first**, or every binary file lands in
  `skipped_files` and `test_search_files_skips_binary_files` (`test_search.py:427`) fails.
- **Both `resolve()` calls must sit inside the same `try`.**
  `patch.object(Path, "resolve", side_effect=OSError)` patches *every* `resolve`, so
  whichever runs first raises.
- **No `".." in parts` check inside the `OSError` handler.** The `..` guard is hoisted above
  `resolve()`, so a second check there is dead code.
- **On Windows `Path("/tmp/x").is_absolute()` is `False`.** New absolute-branch tests must
  build paths from `tmp_path`, never from a hardcoded POSIX string, or they silently test
  the relative path on Windows.
- **Variant 2 is only verified on CI.** Symlink creation fails locally with `WinError 1314`;
  those tests skip on Windows without Developer Mode. Local green ≠ variant 2 verified.
  Every CI job is `ubuntu-latest` / Python 3.11.
- **These tests must pass unchanged:** `test_normalize_path_absolute`,
  `test_normalize_path_relative`, `test_normalize_path_security_error_absolute`,
  `test_normalize_path_security_error_relative`, both `..._oserror_...` tests,
  `test_move_symlinks` (`test_move_operations.py:312`), `test_save_file_security`,
  `test_read_file_security`, `test_delete_file_security`, `test_append_file_security`,
  `test_search_files_skips_binary_files`, and the `list_directory` tests at
  `tests/test_server.py:175, :250, :269` plus `test_tree_listing.py:37-64`. If one needs
  editing, the contract has shifted further than intended — stop and re-read this summary.

## Checks (every step)

`mcp__mcp-tools-py__run_format_code`, then `run_pylint_check`, `run_pytest_check` with
`extra_args: ["-n", "auto"]`, and `run_mypy_check`. Step 1 also runs `run_ruff_check` and
`run_vulture_check` because `import os` is removed.
