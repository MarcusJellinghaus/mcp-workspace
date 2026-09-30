# Step 1: Formatter renders the linked-branches line

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_1.md`) for
issue #303. Write the tests first, then the implementation. Run `run_format_code`, pylint,
pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Produce one commit.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — `format_issue_view`
- `tests/github_operations/test_formatters.py` — class `TestFormatIssueView`

## WHAT

```python
def format_issue_view(
    issue: IssueData,
    comments: list[CommentData],
    max_lines: int = 200,
    *,
    linked_branches: list[str] | None = None,
    include_linked_branches: bool = False,
) -> str:
```

Existing callers stay valid (server passes `max_lines` positionally; tests use
`comments=[]`). Document both new arguments in the docstring.

## HOW

No new imports. The line is appended to the existing State/Labels/Assignees string with a
single `\n`, not added as its own `parts` entry.

## ALGORITHM

```
header = f"State: ... | Labels: ... | Assignees: ..."     # unchanged
if include_linked_branches:
    if linked_branches is None: value = "unknown (lookup failed)"
    else: value = ", ".join(linked_branches) or "none"
    header += f"\nLinked branches: {value}"
parts.append(header)
```

## DATA

Returns the same string as before, plus `Linked branches: <value>` as output line 4 when
requested.

## Tests (write first)

In `TestFormatIssueView`:

- `test_format_issue_view_linked_branches` — `@pytest.mark.parametrize` over
  `(linked_branches, expected_line)`:
  - `["1176-adopt-deptry"]` → `Linked branches: 1176-adopt-deptry`
  - `["12-a", "12-b"]` → `Linked branches: 12-a, 12-b`
  - `[]` → `Linked branches: none`
  - `None` → `Linked branches: unknown (lookup failed)`

  Call with `include_linked_branches=True` and assert
  `result.splitlines()[3] == expected_line` (checks form and position).
- `test_format_issue_view_linked_branches_not_requested` — default call, and a call with
  `linked_branches=["x"]` but the flag off: `"Linked branches" not in result`.
- `test_format_issue_view_linked_branches_survives_max_lines_4` — long body, `max_lines=4`,
  flag on: the line is still in the result.
