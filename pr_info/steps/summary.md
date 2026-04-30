# Issue #180 — Honor `commit.gpgsign` in `commit_staged_files`

## Goal

Switch `commit_staged_files()` from GitPython plumbing (`repo.index.commit`) to
porcelain (`repo.git.commit`) so all of git's signing-related config and hooks
are honored automatically. Add a typed `error_category` field to `CommitResult`
so callers can branch on signing-failed vs commit-failed vs validation-failed
without parsing locale-dependent stderr.

## Architectural / Design Changes

| Area | Change |
|---|---|
| Git invocation pattern | Plumbing → porcelain in `commit_staged_files()` only. Inherits `commit.gpgsign`, `user.signingkey`, `gpg.format`, `gpg.program`, and pre-commit / commit-msg hooks. |
| Hook policy | **Behavior change**: hooks now run by default (no `--no-verify`). `repo.index.commit` silently bypassed them; porcelain doesn't. Documented in docstring; flagged for downstream `mcp-coder` users in the PR description. |
| `CommitResult` schema | Add `error_category: Optional[Literal["signing_failed", "commit_failed", "validation_failed"]]`. `None` on success; populated on every failure path. `total=True` (default) so mypy catches any dict literal that forgets the field. |
| Error classification | Case-insensitive substring match on `GitCommandError.stderr` against `["gpg", "signing", "secret key", "signing failed"]` → `signing_failed`; other `GitCommandError`s → `commit_failed`; pre-git validation → `validation_failed`. Locale-dependent (English keywords); non-English falls through to `commit_failed` with raw stderr still in `error`. |
| Exception handling | Drop the broad `except Exception` clause in `commit_staged_files()` only (resolves the existing `# TODO: narrow to GitCommandError`). Same TODO in `workflows.py` and `core.py` is **out of scope**. |
| Debug logging | Single debug line with command args + signing-related config (`commit.gpgsign`, `gpg.format`, `user.signingkey`) read via `repo.config_reader().get_value(..., default="<unset>")`. On `GitCommandError`, log stderr truncated to the first 500 characters + exit status. Safety net since the test is mock-only. |
| Test fixture hermeticity | All three `git_repo*` fixtures in `tests/git_operations/conftest.py` set repo-local `commit.gpgsign=false` and `tag.gpgsign=false` to override developer/CI `~/.gitconfig`. Otherwise contributors with global signing enabled would see new failures across `test_commits.py`, `test_diffs.py`, `test_file_tracking.py`. |
| Test strategy | **Mock-only** for signing assertions: patch `safe_repo_context` to yield a `MagicMock`; assert `repo.git.commit` is called with `("-m", message)` and **without** `--no-gpg-sign`. Real-GPG end-to-end testing is too brittle across CI runners. |
| `commit_all_changes` | Propagates `error_category` from delegated `commit_staged_files`; populates `validation_failed` for not-a-repo and stage-failure paths; `None` for the no-changes early-return. |
| `rebase_onto_branch` | **No change** — already uses porcelain via `repo.git.rebase(...)` and inherits `rebase.gpgSign` / `commit.gpgsign` automatically. |

## Files Modified (no new source files, no module restructure)

```
src/mcp_workspace/git_operations/
  core.py                       # CommitResult: add error_category field
  commits.py                    # porcelain swap, classification, logging, drop broad except
  workflows.py                  # populate error_category in commit_all_changes return literals

tests/git_operations/
  conftest.py                   # all three fixtures set commit.gpgsign=false, tag.gpgsign=false
  test_commits.py               # new mock-based tests for arg forwarding, classification, validation
```

No new directories. No new modules. No `__init__.py` re-export changes (`CommitResult` is already exported and the schema change is additive).

## Out of Scope

- New `verify_git` function (separate issue).
- `run_hooks` opt-out flag — hooks just run; no toggle.
- Refactoring `commit_all_changes` staging orchestration.
- The `# TODO: narrow to GitCommandError` in `workflows.py` and `core.py`.
- `mcp-coder` re-export changes (it inherits the fix verbatim; downstream release notes should flag the hooks-now-run behavior change).
- Real-gpg end-to-end test.

## Acceptance Criteria (mirroring the issue)

- `commit_staged_files()` invokes `repo.git.commit("-m", message)` without `--no-gpg-sign` (verified by mock test).
- `CommitResult` includes a populated `error_category` on every failure path; `None` on success. Categories map per the taxonomy.
- Signing-flavoured `GitCommandError`s → `signing_failed`; other `GitCommandError`s → `commit_failed`; pre-git validation → `validation_failed`.
- `commit_all_changes` propagates `error_category` correctly.
- Strong debug logging in place (args + signing config + stderr/exit on failure).
- Hooks-now-run-by-default documented in the function docstring and PR description.
- Fixtures set `commit.gpgsign=false` and `tag.gpgsign=false`.
- Existing tests still pass; new mock-based tests cover signing-arg forwarding and category classification.
- Broad `except Exception` removed from `commits.py`.

## Implementation Steps (one commit each)

1. **`step_1.md`** — Harden test fixtures: set repo-local `commit.gpgsign=false` and `tag.gpgsign=false` in all three `git_repo*` fixtures. Independent, risk-reducing prerequisite.
2. **`step_2.md`** — Add `error_category` field to `CommitResult` (typed `Literal`), thread `error_category=None` through all existing dict-literal returns: 6 sites in `commits.py` and 4 sites in `workflows.py` (10 total). Mechanical plumbing; no behavior change. Mypy `total=True` enforces completeness.
3. **`step_3.md`** — Porcelain swap in `commit_staged_files()`: replace `repo.index.commit(...)` with `repo.git.commit("-m", ...)`, add stderr-substring classification, drop broad `except Exception`, add debug logging of args + signing config, populate `error_category` on every failure path. Update `commit_all_changes` validation paths to populate `validation_failed`. New mock-based tests for arg forwarding, signing classification, and validation. Update docstring to flag hooks-run-by-default.
