# Summary — #411: report unreadable fields instead of wrong values (fine-grained PATs)

## Goal

Stop two GitHub lookups from reporting wrong values when a fine-grained PAT cannot read a field:

1. `verify_github` reports `auto_delete_branches` as "not enabled" when GitHub omitted
   `delete_branch_on_merge` (token lacks Contents: Read and write). It must report "not accessible" instead.
2. The check-lookup error text names a permission fine-grained PATs do not have ("Checks: read")
   and labels a 401 as a missing permission. Fix the 403 text, split out 401, and fix the skill row
   that repeats the wrong advice.

The texts below are quoted by MarcusJellinghaus/mcp_coder#1446 — use them **exactly**:

| Where | Text |
|---|---|
| `auto_delete_branches` value when unreadable | `not accessible — token lacks Contents: Read and write` |
| `auto_delete_branches` error when unreadable | `merge settings not returned by GitHub` |
| `PERMISSION_ERROR_TEXT` (403) | `token lacks permission (Commit statuses: read; fine-grained PATs cannot read check runs)` |
| `TOKEN_REJECTED_ERROR_TEXT` (401) | `token rejected (401)` |

## Architectural / design changes

No new modules, functions, or data structures. Two small behaviour changes in existing code:

- **Tri-state `auto_delete_branches` row.** `delete_branch_on_merge` is read into a local annotated
  `bool | None`. `None` → `ok=None` warning row with the permission hint in the *value* (mcp_coder's
  `verify` only prints `error` for `branch_protection` rows). Truthy → unchanged "auto-delete on merge";
  `False` → unchanged "not enabled". Severity stays `warning`, so `overall_ok` is unaffected.
  - The local annotation is required: PyGithub types the attribute as `bool`, so a bare
    `is None` check is flagged unreachable by mypy (`warn_unreachable`).
  - The enabled branch stays a truthiness test (not `is True`) — several test stubs never set the
    attribute and return a truthy `Mock`.
  - Do **not** test `"delete_branch_on_merge" in repo.raw_data` — `raw_data` is a `Mock` in the test
    stubs and the membership test raises `TypeError`.
- **401 / 403 split in `_classify_lookup_error`.** Rate-limit detection keeps precedence; 403 →
  `PERMISSION_ERROR_TEXT` (new wording); 401 → new module constant `TOKEN_REJECTED_ERROR_TEXT`,
  matching how `verification.py` and `_permission_probes.py` label a 401. Other errors unchanged.
  The return contract of `get_non_green_checks` is unchanged.
- **Skill row.** The `could not list checks: …` row in the `check_branch_status` skill gets the
  corrected remedy (Commit statuses: read; classic PAT with `repo` scope for private repos; replace a
  rejected token; wait for rate-limit reset).

## Files modified

No files or folders are created (besides these plan files).

| File | Step | Change |
|---|---|---|
| `src/mcp_workspace/github_operations/verification.py` | 1 | `None` branch for `auto_delete_branches` |
| `tests/github_operations/test_verification.py` | 1 | widen `delete_branch_on_merge` to `bool \| None`; add not-accessible test |
| `src/mcp_workspace/github_operations/pr_checks_mixin.py` | 2 | new 403 text, new 401 constant, split in `_classify_lookup_error`, docstring |
| `tests/github_operations/test_pr_checks_mixin.py` | 2 | add 401 test |
| `tests/checks/test_branch_status_non_green_checks.py` | 2 | refresh copied `_REASON` string |
| `.claude/skills/check_branch_status/SKILL.md` | 2 | new action text for the `could not list checks` row |

## Steps

- [Step 1](./step_1.md) — `auto_delete_branches` reports "not accessible" when the field is unreadable.
- [Step 2](./step_2.md) — check-lookup 403/401 texts and the skill row.

The two steps are independent; each is one commit.

## Out of scope

- Naming which call failed in the check lookup, or keeping statuses when check runs fail.
- Classic-token wording in the auto-delete hint.
- Any change to mcp_coder's `verify` rendering.
- Turning the auto-delete row into a Contents-write probe (`_permission_probes.py` has no write probes by design).
