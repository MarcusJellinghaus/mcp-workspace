# Summary — #350 verify_github: support GitHub rulesets in branch protection checks

## Problem
`verify_github()` reads branch protection only from the classic API
(`GET /repos/{o}/{r}/branches/{b}/protection`). A branch protected by rulesets gets a 404 there
and is reported as "not configured". The fix also reads the effective-rules endpoint
(`GET /repos/{o}/{r}/rules/branches/{b}`), merges both sources, and adds a sixth row,
`require_pull_request`.

## Architectural / design changes

### Two sources, one fact type
Each source becomes a `ProtectionFacts` (frozen dataclass), or `None` when that source did not answer:

| Field | Classic | Rulesets |
|---|---|---|
| `protected` | protection object exists | any effective rule exists |
| `checks_required` | `required_status_checks is not None` | `required_status_checks` rule present (zero contexts still counts) |
| `contexts` | `required_status_checks.contexts` | `parameters.required_status_checks[].context` |
| `strict` | `required_status_checks.strict` | `parameters.strict_required_status_checks_policy` |
| `force_push_blocked` | `not allow_force_pushes` | `non_fast_forward` rule present |
| `deletion_blocked` | `not allow_deletions` | `deletion` rule present |
| `require_pr` | `required_pull_request_reviews is not None` | `pull_request` rule present |

Every field defaults to `False`, so `ProtectionFacts()` is the answered "no". Classic
"Branch not protected" and `facts_from_rules([])` both produce it.

### `merge` is the only place that decides
`merge(classic, rules)` returns a `ProtectionFacts` whose flags are `bool | None`. Per flag:
- `True` if either answered source is `True`;
- `False` if both sources answered and neither is `True`;
- `None` otherwise (one source did not answer).

`contexts` is the union of the answered sources. This one rule covers the whole `ok=None` matrix
in the issue: a positive is never downgraded, and a negative needs both sources to have answered.

### One row-building path
`verification.py` replaces the old if/else block for checks 5–9 with:
- `_protection_result(outcome, rules_outcome)`: builds both sides, merges them, and handles the two
  special cases:
  - no outcome → `unknown` rows (unchanged);
  - `merged.protected is False` → every row "not configured" / "no branch protection" (unchanged).
- `_rows_from_facts(facts, source_label, *, reason, error)`: maps each flag to a row. `True`/`False`
  keep today's value texts; `None` gives `ok=None` with value `reason`.

A classic failure combined with an empty rules answer now goes through the same path. It produces
exactly today's `ok=None` rows, so `TestProtectionOutcomeTable` stays green unchanged.

### Shared reason and error
- `reason` (the value text of an `ok=None` row) comes from the first source that did not answer,
  classic first.
- `error` joins the notes of every source that did not answer with `"; "` and goes on all six rows.
  It is omitted when both sources answered.

### The GHE 404 rule lives in one place
A 404 from the rules endpoint counts as answered-empty (`ProtectionFacts()`) only when classic said
"Branch not protected". Any other rules failure means the rules side did not answer, and its note is
`rulesets not verifiable: <short reason>`.

### Raw requests
PyGithub has no ruleset wrapper. `fetch_rules(manager, repo, branch)` uses the private-requester
pattern from `_pr_feedback_sources.py` (`requestJsonAndCheck`):
- the branch name in the URL is URL-quoted, and both calls use `per_page=100`;
- it does a best-effort `GET /rulesets` name lookup, filtered to the `ruleset_id`s found in the rules.

### Unchanged
- `_permission_probes.py` still receives only the classic `ProtectionOutcome`;
  `perm_administration_read` reflects the classic call only.
- Severity stays `warning`, so exit codes are unaffected.

## Files

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/_ruleset_protection.py` | **new**: `ProtectionFacts`, `facts_from_classic`, `facts_from_rules`, `merge`, `source_label`, `fetch_rules` |
| `src/mcp_workspace/github_operations/_types.py` | add `RulesOutcome`; receives `short_reason` (moved from `verification._short_reason`) |
| `src/mcp_workspace/github_operations/verification.py` | `require_pull_request` key, rules fetch in the guard, `_protection_result`, `_rows_from_facts`, wording updates |
| `tests/github_operations/test_ruleset_protection.py` | **new**: table tests for the pure functions and mocked-HTTP tests for `fetch_rules` |
| `tests/github_operations/test_verification.py` | autouse `fetch_rules` stub, `_make_mock_protection` parameter, `BRANCH_CHECK_KEYS`, matrix tests, wording updates |

## Steps
1. `step_1.md`: pure facts module (`ProtectionFacts`, `facts_from_classic`, `facts_from_rules`, `merge`, `source_label`).
2. `step_2.md`: `RulesOutcome`, move `short_reason`, add `fetch_rules`.
3. `step_3.md`: classic-only refactor of checks 5–9 into `_protection_result` / `_rows_from_facts`,
   plus the new `require_pull_request` row; the existing tests guard it.
4. `step_4.md`: wire `fetch_rules` and the classic/rules merge into `verify_github`; autouse stub
   and matrix tests.
5. `step_5.md`: record the read-only fine-grained token check in the module docstring if a result
   is available, otherwise flag it as open in the PR description (non-blocking).

## Out of scope
Required approvals count, linear history, a new `perm_*` row, and pagination beyond 100.
