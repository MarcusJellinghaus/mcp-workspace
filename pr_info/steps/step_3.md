# Step 3 — `reference_name` routing tests

Read [summary.md](./summary.md) first. Depends on Step 2. Tests only — no source
change is expected. If a test here fails, the fix belongs in `server.py`.

## WHERE

Modified:

- `tests/github_operations/test_github_write_tools_reference.py`

## WHAT

Extend the existing parametrised routing table (around line 111) with the three
new tools:

```python
_TOOL_CASES = [
    (github_label_list, {}),
    (github_issue_comment, {"number": 42, "body": "hi"}),
    (github_issue_create, {"title": "T"}),
    (github_issue_edit, {"number": 42, "title": "T"}),
    (github_subissue_add, {"parent_number": 42, "child_number": 43}),
    (github_subissue_list, {"parent_number": 42}),
    (github_subissue_remove, {"parent_number": 42, "child_number": 43}),
]
_TOOL_IDS = [
    "label_list", "issue_comment", "issue_create", "issue_edit",
    "subissue_add", "subissue_list", "subissue_remove",
]
```

## HOW

- Import the three tools from `mcp_workspace.server` alongside the existing ones.
- Both existing parametrised tests — `test_reference_name_uses_repo_url` and
  `test_no_reference_name_uses_project_dir` — pick the new cases up with no
  further change. They assert only how `IssueManager` was constructed
  (`{"repo_url": "https://github.com/owner/sibling"}` versus
  `project_dir`), so the mocked manager's return value does not matter.
- The file's local `_make_manager()` returns a `MagicMock`, so
  `add_sub_issue`/`list_sub_issues` auto-return Mocks and the tools render a
  harmless Mock repr. No new fixture is needed. Only add a stub return value if
  one of these tests starts asserting on tool output, which it should not.
- Use distinct parent and child numbers (42/43): equal numbers would hit the
  self-link guard and return before `IssueManager` is ever constructed, so the
  routing assertion would fail for the wrong reason.

## ALGORITHM

None — this step only extends existing parametrised data.

## DATA

`_TOOL_CASES: list[tuple[Callable[..., str], dict[str, Any]]]` and the matching
`_TOOL_IDS: list[str]`, both already defined in the file.

## Checks

`run_format_code`, then pylint, pytest `-n auto`, mypy, vulture, ruff,
lint-imports.

## Commit

`test(server): cover reference_name routing for sub-issue tools (#294)`

## LLM prompt

> Implement Step 3 of the sub-issue tools feature for issue #294. Steps 1 and 2
> are already committed.
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md` first.
> In `tests/github_operations/test_github_write_tools_reference.py`, import
> `github_subissue_add`, `github_subissue_list` and `github_subissue_remove` and
> add them to `_TOOL_CASES` and `_TOOL_IDS` as shown in step_3. Use parent 42 and
> child 43 — equal numbers would trip the self-link guard before `IssueManager`
> is constructed. Expect no source change; if a test fails, fix `server.py`.
> Then run `run_format_code` followed by pylint, pytest (`extra_args=["-n","auto"]`),
> mypy, vulture, ruff and lint-imports, and make one commit.
