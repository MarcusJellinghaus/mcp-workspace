# Step 3 — Create `test_base.py` (move `validate_*` + NEW `parse_base_branch`)

> Read `pr_info/steps/summary.md` first. This is Step 3 of 6. One commit.
> Must run **before** Step 4 (both touch the core file).

## Kind
Extract-and-relocate + TDD new coverage. `base.py` tests are currently embedded in
`test_issue_manager_core.py` as two methods; extract them so the core file is decomposed by
concern. Additionally backfill `parse_base_branch`, which currently has **zero** coverage.

## WHERE
- New file: `tests/github_operations/issues/test_base.py`
- Modified: `tests/github_operations/test_issue_manager_core.py` — remove the two
  `test_validate_*` methods (and, if now unused there, the `validate_*` imports).

## WHAT — functions under test (`issues/base.py`)
```python
def validate_issue_number(issue_number: int) -> bool     # raises ValueError if <= 0 or non-int
def validate_comment_id(comment_id: int) -> bool         # raises ValueError if <= 0 or non-int
def parse_base_branch(body: str) -> Optional[str]        # heading "Base Branch" -> branch/None; ValueError on multi-line
```

## HOW — imports
```python
import pytest
from mcp_workspace.github_operations.issues.base import (
    parse_base_branch,
    validate_comment_id,
    validate_issue_number,
)
```
Lift the two existing tests **verbatim** (as plain module-level functions; drop the unused
`self`/`tmp_path`). They need no fixtures and no `git_integration` marker.

**Do NOT** remove the `validate_*` imports from `test_comments_mixin.py`,
`test_events_mixin.py`, or `test_labels_mixin.py` — they use them as helpers (untouched).

## ALGORITHM (test logic)
```
# moved verbatim:
test_validate_issue_number:   pytest.raises(ValueError) for 0 and -1; assert True for 1, 999
test_validate_comment_id:     pytest.raises(ValueError) for 0 and -1; assert True for 1, 999

# NEW parse_base_branch (pure string -> branch/None, no mocking):
test_happy_path:              "### Base Branch\n\nfeature/v2\n\n### Description" -> "feature/v2"
test_empty_body:              "" -> None
test_any_heading_level:       "# Base Branch\n\nx" and "###### Base Branch\n\nx" -> "x"
test_case_insensitive:        "### base branch\n\nx" -> "x"
test_no_match:                "### Description\n\nno base branch here" -> None
test_empty_content:           "### Base Branch\n\n### Next" -> None
test_multiline_raises:        "### Base Branch\n\nline1\nline2\n" -> pytest.raises(ValueError)
```

## DATA
`validate_*` return `bool` / raise `ValueError`. `parse_base_branch` returns
`Optional[str]` / raises `ValueError` on malformed multi-line content.

## Verify (MCP tools only)
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","tests/github_operations/issues/test_base.py"])`
  — moved + new tests pass.
- `mcp__tools-py__run_pytest_check(extra_args=["-n","auto","tests/github_operations/test_issue_manager_core.py"])`
  (keep git markers) — core still passes without the two removed methods.
- `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_mypy_check`.

## Done when
`test_base.py` holds the two moved `validate_*` tests plus the new `parse_base_branch`
tests; core no longer defines them; all pass; checks green. One commit.

## LLM prompt
> Implement Step 3 from `pr_info/steps/step_3.md` (context in `pr_info/steps/summary.md`).
> Create `tests/github_operations/issues/test_base.py`: move the two `test_validate_*`
> tests out of `tests/github_operations/test_issue_manager_core.py` **verbatim** (as
> module-level functions) and add new `parse_base_branch` tests per the ALGORITHM section.
> Remove those two methods (and now-unused imports) from the core file, but leave the
> `validate_*` helper imports in the comments/events/labels files untouched. Verify both
> files with `mcp__tools-py__run_pytest_check`, then pylint and mypy. Follow all
> `CLAUDE.md` rules (MCP tools only; `./tools/format_all.sh` before committing). Produce
> exactly one commit.
