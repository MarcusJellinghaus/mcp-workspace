# Step 11 — A4 docstrings

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 11 only: docstring changes, no
behaviour change, no new tests. Run the checks from the summary, format, commit as one commit.

## WHERE
- `src/mcp_workspace/git_operations/branch_queries.py`
- `src/mcp_workspace/git_operations/repository_status.py`

## WHAT (add a "Note:" paragraph to each docstring)
- `remote_branch_exists`: reads local `origin/*` refs — no network, stale both ways, returns
  `False` with no reason. For an authoritative answer use `probe_origin_branch`.
- `is_git_repository`: does not spawn git (opens `Repo` with
  `search_parent_directories=False`); `True` for bare repositories, where
  `rev-parse --is-inside-work-tree` prints `false`.
- `get_full_status`: swallows errors into empty lists, so a failure reads as "clean". Do not
  gate destructive actions on it; use `get_working_tree_status`.
- `is_working_directory_clean`: raises `ValueError` only for a non-repo; otherwise inherits
  `get_full_status` and returns `True` on error. Do not gate destructive actions (e.g. a
  directory delete) on it; use `get_working_tree_status`.
- `get_current_branch_name`: returns `None` on detached HEAD (`rev-parse --abbrev-ref HEAD`
  would print `"HEAD"`).

## HOW / ALGORITHM / DATA
Docstrings only.
