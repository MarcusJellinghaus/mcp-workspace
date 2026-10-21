# Step 1 — Linked Branch wording for `LINKED_VIA_PR`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> TDD: update the tests first, see them fail, then change the code. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/checks/branch_status_rendering.py` — `_format_linked_branch_line`
- `tests/checks/test_branch_status_linked_branch.py` — `test_state_renders_one_line` (around line 311) and its `LINKED_VIA_PR` parametrize case
- `.claude/skills/check_branch_status/SKILL.md` — `LINKED_VIA_PR` row

## WHAT

No new functions. Change only the `LinkedBranchStatus.LINKED_VIA_PR` branch of
`_format_linked_branch_line(report) -> Optional[str]`. The enum value `LINKED_VIA_PR` stays.

## HOW

Replace

```python
text = f"LINKED_VIA_PR — {issue} closed by PR #{pr.number} ('{current}')"
```

with

```python
text = (
    f"OK via PR #{pr.number} — PR branch matches current branch '{current}' "
    f"(closes {issue}; no branch linked in the Development panel)"
)
```

`issue` is the existing local (`issue #N` or `the issue`). `current` is `report.branch_name`, which
for this state equals `pr.head_ref_name`. Print the full branch name and never shorten it. Update
the function docstring only if it mentions the old wording.

Both formats call `_format_linked_branch_line`, so this one change covers human and LLM output.

## Tests (write first)

In `test_state_renders_one_line`, replace

```python
assert lines[0].startswith(f"Linked Branch: {status.value}")
```

with a per-state prefix:

```python
prefix = "OK via PR" if status == LinkedBranchStatus.LINKED_VIA_PR else status.value
assert lines[0].startswith(f"Linked Branch: {prefix}")
```

For the `LINKED_VIA_PR` parametrize case (`ClosingPRRef(10, "255-feature")`), set expected substrings to:

- `"OK via PR #10"`
- `"PR branch matches current branch '255-feature'"`
- `"closes issue #255"`
- `"no branch linked in the Development panel"`

and forbidden substrings to `["LINKED_VIA_PR"]`. Use the branch and issue numbers from the existing
`_make_report` helper; adjust the literals if they differ. Add one test with a long branch name
(more than 80 characters) in `LINKED_VIA_PR` state that asserts the full name appears verbatim in
both formats (use the existing `_FORMATTERS` parametrize).

## SKILL.md

Replace the row

```
| Linked branch `LINKED_VIA_PR` | Already satisfies the check — no action needed |
```

with

```
| Linked branch `OK via PR` | Already satisfies the check — no action needed |
```

## DATA

The rendered line is a string; the report and enum are unchanged.
