# Step 8 — `github_issue_view(body_file=…)` with round-trip tests

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_8.md`: add the `body_file`
> parameter to `github_issue_view`, using the step 6 formatter and the step 7 helpers, and add the
> round-trip tests. Write the tests first. Run pylint, pytest (`-n auto`) and mypy, all green.
> Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/toolset/github_read.py` — `github_issue_view` (`:42`)
- `tests/github_operations/test_github_issue_view_body_file.py` — add tool-level tests

## WHAT

```python
body_file: Annotated[
    str | None,
    Field(description=(
        "Workspace path to write the raw issue body to, byte for byte (no header, no "
        "truncation, no comments, line endings kept); the reply shows a pointer line instead "
        "of the body. Always a workspace path, also with reference_name. Overwrites the file."
    )),
] = None,
```

Docstring additions:
- The rendered view is display-only; do not feed it back as a body.
- For read-modify-write, use `body_file` → `edit_file` → `github_issue_edit(body_file=…)`.
- `body_file` writes a project file, even though the tool is registered read-only.
- `body_file` is always a workspace path, also when `reference_name` is set.

## HOW

- Import `check_body_target` and `save_body` from `mcp_workspace.toolset._github_write_helpers`.
- Everything stays inside the existing `try/except Exception → tool_error(e)`, so a refused path
  or a write error returns `tool_error` and no view.
- Fetch issue, comments and linked branches **before** `save_body`, so an API error never leaves
  a file behind.

## ALGORITHM

```
target = check_body_target(ctx, body_file) if body_file is not None else None   # before GitHub
manager = issue_manager(ctx, reference_name); issue = manager.get_issue(number)
if not issue["number"]: <unchanged not-found / repo-access error>
comments = ...; linked = ...; trusted = ...                                      # unchanged
body_note = save_body(*target, issue["body"]) if target else None
return format_issue_view(..., body_note=body_note)
```

## Tests (mock `mcp_workspace.github_operations.issues.IssueManager`, as in `test_github_read_tools_issues.py`)

- **Writes the body:**
  - a 1000-line CRLF non-ASCII body is written byte for byte (no header, no truncation, no
    comments, no BOM);
  - the reply has the pointer line (`1000 lines, CRLF`), the header and the comments;
  - the reply does not contain the body.
- **Edge cases:**
  - empty body → 0-byte file;
  - an existing file is overwritten;
  - an untrusted author → title fenced, pointer outside the fence, file holds the unfenced body;
  - `reference_name` set (reuse the reference setup pattern from
    `test_github_read_tools_reference.py`) → file lands under the workspace `project_dir`.
- **Writes nothing and returns `Error`:**
  - outside, gitignored and directory paths, with the manager never constructed;
  - issue not found;
  - `get_issue` / `get_comments` raising.
- **Without `body_file`:** output is identical to today's (compare against a direct
  `format_issue_view` call, or reuse an existing assertion).
- **Round trip, no edit.** View a 500+ line CRLF body with `body_file`, then
  `github_issue_edit(number, body_file=same path)`. Assert the `body` kwarg passed to
  `edit_issue` equals the original byte for byte. Patch `mcp_workspace.toolset.github_write.issue_manager`
  too if the class patch does not reach `github_issue_edit`. Have `edit_issue` return the edited
  issue.
- **Round trip with `edit_file`.** Parametrize over a 500+ line LF body and a CRLF body: view →
  `tools["edit_file"]` changes one unique line → `github_issue_edit(body_file=…)`. Compare the
  sent body with the original: line endings identical, and only the edited line differs (compare
  `split` lists on the body's own ending). `edit_file` lives in the `workspace.write` group
  (`toolset/write.py:118`) and is `async`: register that group too and
  `await tools["edit_file"](…)`, following `tests/file_tools/test_edit_file_api.py`.
