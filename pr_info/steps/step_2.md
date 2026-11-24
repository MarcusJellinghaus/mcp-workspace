# Step 2 — check-lookup errors: correct 403 text, separate 401, fix skill row

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> Follow TDD: write the test changes first, then the code and skill changes. Use the exact strings given.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and `run_ruff_check`; all must pass.
> Run `run_format_code`, then make one commit.

## Precondition

`_classify_lookup_error` in `src/mcp_workspace/github_operations/pr_checks_mixin.py` contains
`e.status in (401, 403)`. If it does not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `tests/github_operations/test_pr_checks_mixin.py`
- `tests/checks/test_branch_status_non_green_checks.py`
- `src/mcp_workspace/github_operations/pr_checks_mixin.py` — module constants and `_classify_lookup_error()`
- `.claude/skills/check_branch_status/SKILL.md` — "Follow-Up Actions" table

## WHAT

```python
PERMISSION_ERROR_TEXT = (
    "token lacks permission (Commit statuses: read; fine-grained PATs cannot read check runs)"
)
TOKEN_REJECTED_ERROR_TEXT = "token rejected (401)"  # noqa: S105 -- user-facing error text, not a credential

def _classify_lookup_error(e: BaseException) -> str  # signature unchanged
```

New test in `class TestGetNonGreenChecks`:

```python
def test_token_rejected_error(self, checks_env: tuple[PullRequestManager, MagicMock]) -> None
```

## Tests (write first)

1. `tests/github_operations/test_pr_checks_mixin.py`:
   - Import `TOKEN_REJECTED_ERROR_TEXT` next to `PERMISSION_ERROR_TEXT`.
   - Add `test_token_rejected_error` directly after `test_permission_error`, same shape, status `401`:
     ```python
     """401 without rate-limit headers -> TOKEN_REJECTED_ERROR_TEXT."""
     manager, mock_repo = checks_env
     commit = _set_checks(mock_repo, [], [])
     commit.get_check_runs.side_effect = GithubException(
         401, {"message": "Bad credentials"}, headers={}
     )
     assert manager.get_non_green_checks(1, head_sha="abc") == ((), TOKEN_REJECTED_ERROR_TEXT)
     ```
   - `test_permission_error` (403) compares against the constant — no change.
2. `tests/checks/test_branch_status_non_green_checks.py`: set
   `_REASON = "token lacks permission (Commit statuses: read; fine-grained PATs cannot read check runs)"`.

## HOW / ALGORITHM

`_classify_lookup_error`:

```python
msg = format_rate_limit_error(e)
if msg is not None:
    return msg                       # rate limit keeps precedence
if isinstance(e, GithubException):
    if e.status == 403: return PERMISSION_ERROR_TEXT
    if e.status == 401: return TOKEN_REJECTED_ERROR_TEXT
return _format_error_message(e)      # unchanged
```

Update the docstring's `Returns:` to: the rate-limit message, `PERMISSION_ERROR_TEXT` for 403,
`TOKEN_REJECTED_ERROR_TEXT` for 401, or the generic formatted error message.

No import changes in `pr_checks_mixin.py`; `__all__` stays `["PRChecksMixin"]` (tests already import
`PERMISSION_ERROR_TEXT` directly from the module).

## Skill row

In `.claude/skills/check_branch_status/SKILL.md`, replace the action cell of the
`` `mergeable_state=unstable — could not list checks: …` `` row with:

```
Grant the token "Commit statuses: read" (fine-grained PATs cannot read check runs — on a private repo use a classic PAT with `repo` scope), replace the token if it was rejected (401), or wait for the rate-limit reset shown
```

Leave every other row unchanged.

## DATA

`get_non_green_checks` return contract unchanged: `((), reason)` on failure, where `reason` is now:

| Failure | `reason` |
|---|---|
| rate limit (any status) | rate-limit message (unchanged) |
| 403 | `token lacks permission (Commit statuses: read; fine-grained PATs cannot read check runs)` |
| 401 | `token rejected (401)` |
| other | `_format_error_message(e)` (unchanged) |

## Commit message

```
fix(pr_checks): correct check-lookup permission text, split out 401
```
