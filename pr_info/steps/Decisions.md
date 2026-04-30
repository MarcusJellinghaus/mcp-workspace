# Plan review round 1 — decisions log

This file records decisions explicitly made during the plan review round 1
discussion for issue #181 (`verify_git`). Only decisions discussed in the
review are listed here.

## Round 1 decisions

### D-A. Logging library — answered (B): use `mcp_coder_utils.log_utils`

User direction: the new module `git_operations/verification.py` uses
`mcp_coder_utils.log_utils` (per CLAUDE.md "Shared Libraries"), not plain
`logging.getLogger(__name__)`.

- `verification.py` imports
  `from mcp_coder_utils.log_utils import setup_logging, log_function_call`.
- `verify_git` and the non-trivial helpers (`_get_config`, `_run`,
  later `_run_with_input`) are decorated with `@log_function_call`.
- This deliberately **diverges from `github_operations/verification.py`**,
  which still uses plain `logging`. Per CLAUDE.md and explicit user
  direction, the new module follows the project convention rather than
  the parallel module.

Recorded in: `summary.md` ("Design choices"), `step_1.md` (HOW section).

### D-B. ssh `signing_key_accessible` scope — answered (A): file-existence only

User direction: ssh branch of `signing_key_accessible` checks file existence
only at the configured `user.signingkey` path. Agent-loaded SSH keys are
**not** detected. This limitation is documented in the plan's "Out of scope".

- `step_5.md` ssh branch: `Path(user.signingkey).is_file()` only.
- Wording "matches a loaded key" removed from `step_5.md`.
- "Out of scope" entry added to `summary.md`.

Recorded in: `summary.md` ("Out of scope"), `step_5.md` (WHAT table).

## Straightforward (auto-approved) refinements applied in this round

These are minor consistency / coverage refinements that do not change scope
or design. Listed here so the trail is complete.

1. **`step_1.md`**: added `test_run_timeout_propagates` to ensure
   `subprocess.TimeoutExpired` is not swallowed by `_run`.
2. **`step_4.md` / `step_5.md` / `step_6.md`**: clarified that Tier 2 uses
   one shared `safe_repo_context` block opened in step 4 and extended by
   steps 5 and 6 (verify_head deliberately reopens its own context).
3. **`step_7.md`**: added end-to-end happy-path test
   `TestEndToEndHappyPath::test_full_happy_path_all_keys_populated_overall_ok`
   asserting all expected keys present and `overall_ok=True`.
4. **`summary.md`**: added Out-of-scope bullet noting ssh agent-loaded
   keys are not detected (covers D-B).
5. **`step_1.md`**: added explicit assertion that `__all__` in
   `git_operations/__init__.py` remains alphabetised after inserting
   `CheckResult` and `verify_git` (`test_all_remains_alphabetised`).
