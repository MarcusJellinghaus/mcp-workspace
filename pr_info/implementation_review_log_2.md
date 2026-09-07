# review-implementation review log 2

Issue #290 — Security: `normalize_path()` absolute branch never resolves.
Supervised implementation review, run 2.

## Round 1 — 2026-09-07

**Findings**: NO FINDINGS.

The reviewer confirmed a real implementation diff (`path_utils.py`, `search.py`, plus
docstring-only changes in `server.py` and `server_reference_tools.py`) and traced the fix
against all 20 acceptance criteria in the issue:

- Guard order in `normalize_path`: `..` checked on `path_obj.parts` only, explicit NUL
  rejection, both `resolve()` calls inside one `try`, `OSError` fallback with no dead second
  `..` check, final `relative_to` wrapped.
- The `..` message carries both `"traversal"` and `"outside the project directory"`, as the
  six pinned tests require.
- `UnicodeDecodeError` is handled before `except (ValueError, OSError)` in `search.py`, so
  binary files remain a silent skip.
- `_validate_move_parameters` normalizes source and destination before any existence check,
  so the destination parametrization reaches the guard.
- `list_files` normalizes only its directory argument, so the new symlink rejection cannot
  abort the walk that feeds `search_files`.
- Fail-closed on the edges checked: a Windows drive-relative input (`C:foo`) and a resolved
  absolute path against an unresolved `project_dir` both fail containment rather than escape.

**Decisions**: nothing to accept or skip — no findings raised.

**Changes**: none.

**Status**: no changes needed.

## Final Status

Zero code changes this run; rounds 1 and 2 of
[implementation_review_log_1.md](./implementation_review_log_1.md) had already resolved the
earlier findings, and round 3 there was also clean.

| Check | Result |
|---|---|
| pytest (`-n auto`) | 2333 passed, 10 skipped, 0 failed |
| pylint | clean |
| mypy | clean |
| vulture | clean |
| lint-imports | PASSED — 9 contracts kept, 0 broken |
| CI | PASSED |
| Rebase | up to date with base |

The 10 skips are the `@requires_symlinks` tests: symlink creation needs privilege that the
Windows dev machine does not hold. Variant 2 (the symlink escape) is therefore verified by
the `ubuntu-latest` CI job, not locally — as the issue anticipated.

No open issues. The branch is ready for the PR summary.
