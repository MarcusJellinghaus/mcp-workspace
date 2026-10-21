# Step 7 — `github_pr_create` default base follows the issue

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_7.md`). Implement
> step 7 only: tests first, then make `github_pr_create` resolve an omitted `base` for `head`
> via `_resolve_base_branch` and verify it on origin with `origin_has_branch`. Run pylint,
> pytest (`-n auto`) and mypy until green, run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/server.py` — `github_pr_create`
- `tests/github_operations/test_github_pr_create_base.py` (new)
- `tests/github_operations/test_github_write_tools_labels_pr.py` — `TestGithubPrCreate` patches

## WHAT

Signature unchanged. New `Error:` results when `base` is omitted:

| Case | Result |
|---|---|
| Issue section malformed | `Error: issue #N: <sentence>` (from `_resolve_base_branch`) |
| Detection returned `None` | `Error: could not determine base branch for <head>` |
| `origin_has_branch` → `False` | `Error: base branch '<base>' not found on origin` |
| `origin_has_branch` raises | `Error: could not verify base branch '<base>' on origin: <exc>` |

## HOW

- Lazy imports: replace `get_default_branch_name` with
  `from mcp_workspace.git_operations.base_branch import origin_has_branch`
  (keep `get_current_branch_name`).
- Pass the already-built `PullRequestManager` (`manager`) as `pr_manager`.
- An explicit `base` is used unchanged — no resolution, no origin check.
- Remove the old `"could not determine the repository default branch for base"` path.
- Docstring: `base: Target branch (default: resolved for head — the issue's Base Branch, an
  open PR's base, the merge-base parent, or the default branch — and verified on origin)`;
  list the `Error:` cases under Returns.

## ALGORITHM

```
head = head or get_current_branch_name(project_dir); if not head: return <existing error>
if not base:
    base, error = _resolve_base_branch(project_dir, head, manager)
    if error: return error
    if not base: return f"Error: could not determine base branch for {head}"
    try: exists = origin_has_branch(project_dir, base)
    except Exception as e: return f"Error: could not verify base branch '{base}' on origin: {e}"
    if not exists: return f"Error: base branch '{base}' not found on origin"
# existing head == base check, branch-name validation, create_pull_request
```

## DATA

`str` — `"Created PR #<n> — <url>"` or an `Error: …` string; `create_pull_request` is not
called on any error.

## Tests (write first)

Existing `TestGithubPrCreate`: replace the class-level
`@patch("mcp_workspace.git_operations.get_default_branch_name")` with
`@patch("mcp_workspace.server._resolve_base_branch")` (return `("main", None)` where a
default base was expected) and add an autouse fixture in that file patching
`mcp_workspace.git_operations.base_branch.origin_has_branch` to return `True`.
Rewrite `test_base_omitted_uses_default_branch` → asserts `_resolve_base_branch` was called
with `head="feature/y"`.

New file:
- explicit `head` (≠ current branch) → `_resolve_base_branch` called with that head.
- malformed → returns the error; `create_pull_request` not called.
- `(None, None)` → `Error: could not determine base branch for feature/x`; nothing created.
- origin `False` → `Error: base branch 'epic/x' not found on origin`; nothing created.
- origin raises `GitCommandError`/`RuntimeError("boom")` → `Error: could not verify base branch 'epic/x' on origin: …boom…`; nothing created.
- resolved and present → PR created with `base_branch="epic/x"`.
- explicit `base` → neither `_resolve_base_branch` nor `origin_has_branch` called.
