# Step 7 — `check_body_target` / `save_body` helpers

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md`: add
> `check_body_target` and `save_body` to `toolset/_github_write_helpers.py`, next to
> `resolve_body`. Write the tests first. No caller yet. Run pylint, pytest (`-n auto`) and mypy,
> all green. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/toolset/_github_write_helpers.py`. Change the module docstring to
  "Validation and rendering helpers for the workspace.github tools."
- `tests/github_operations/test_github_issue_view_body_file.py` — new (step 8 adds to it)

## WHAT

```python
def check_body_target(ctx: WorkspaceContext, body_file: str) -> tuple[Path, str]:
    """Validate a body_file write target under save_file's path rules.

    Returns:
        (absolute path, project-relative path with forward slashes).

    Raises:
        ValueError: path gitignored / outside the project / an existing directory.
    """

def save_body(abs_path: Path, display_path: str, body: str) -> str:
    """Write body verbatim (UTF-8, no BOM, line endings kept); return the pointer line."""
```

## HOW

- The checks mirror `resolve_body`: `check_not_gitignored(ctx, body_file)`, then
  `normalize_path(body_file, ctx.project_dir)`.
- Import `describe_line_endings` from `mcp_workspace.file_tools.line_endings`.
- Do not use `save_file_util`: it converts line endings.

## ALGORITHM

```
check_body_target: check_not_gitignored; abs_path, rel = normalize_path(...)
    if abs_path.is_dir(): raise ValueError(f"body_file '{body_file}' is a directory")
    return abs_path, rel.replace("\\", "/")
save_body: abs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(abs_path, "w", encoding="utf-8", newline="") as f: f.write(body)
    return f"(body saved to {display_path}: empty)" if not body
           else f"(body saved to {display_path}, {describe_line_endings(body)})"
```

## DATA

Pointer lines: `(body saved to .scratch/issue-251.md, 488 lines, CRLF)`,
`(body saved to x.md, 1 line)`, `(body saved to x.md: empty)`.

## Tests (call the helpers directly with a `WorkspaceContext` for `project_dir`)

- **`check_body_target`:**
  - accepts `.scratch/new/issue.md` (it doesn't exist yet) and returns the forward-slash relative
    path;
  - `"..\\x.md"`-style and `../outside.md` paths → `ValueError`;
  - a gitignored path → `ValueError`;
  - an existing directory → `ValueError`;
  - none of these writes anything.
- **`save_body`:**
  - a CRLF non-ASCII body → `read_bytes() == body.encode("utf-8")` (no BOM, CRLF kept);
  - mixed and CR bodies are kept byte for byte;
  - missing parents are created;
  - an existing file is overwritten;
  - an empty body → 0-byte file and the `: empty` pointer;
  - pointer text for CRLF / LF / mixed / no-break bodies.
