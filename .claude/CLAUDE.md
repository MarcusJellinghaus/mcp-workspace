## About this repo

`mcp-workspace` is an MCP server providing workspace file operations (read, write, edit, list, search) and read-only access to reference projects. Source code is in `src/mcp_workspace/`, tests in `tests/`. Python 3.11+ required.

## MCP Tools — mandatory

**Do NOT use native Claude Code file tools** (`Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`) for any operation that has an MCP equivalent. Always use the `mcp__mcp-workspace__*` tools instead. This applies to all file reading, writing, editing, searching, listing, and git operations.

### Tool mapping

| Task | MCP tool |
|------|----------|
| Read file | `mcp__mcp-workspace__read_file` |
| Edit file | `mcp__mcp-workspace__edit_file` |
| Write file | `mcp__mcp-workspace__save_file` |
| Append to file | `mcp__mcp-workspace__append_file` |
| Delete file | `mcp__mcp-workspace__delete_this_file` |
| Move file | `mcp__mcp-workspace__move_file` |
| List directory | `mcp__mcp-workspace__list_directory` |
| Search files | `mcp__mcp-workspace__search_files` |
| Search reference files | `mcp__mcp-workspace__search_reference_files` |
| Read reference project | `mcp__mcp-workspace__read_reference_file` |
| List reference dir | `mcp__mcp-workspace__list_reference_directory` |
| Get reference projects | `mcp__mcp-workspace__get_reference_projects` |
| Run pytest | `mcp__mcp-tools-py__run_pytest_check` |
| Run pylint | `mcp__mcp-tools-py__run_pylint_check` |
| Run mypy | `mcp__mcp-tools-py__run_mypy_check` |
| Run vulture | `mcp__mcp-tools-py__run_vulture_check` |
| Run lint-imports | `mcp__mcp-tools-py__run_lint_imports_check` |
| Run ruff check | `mcp__mcp-tools-py__run_ruff_check` |
| Run ruff fix | `mcp__mcp-tools-py__run_ruff_fix` |
| Run bandit | `mcp__mcp-tools-py__run_bandit_check` |
| Format code (black+isort) | `mcp__mcp-tools-py__run_format_code` |
| Get library source | `mcp__mcp-tools-py__get_library_source` |
| Refactoring | `mcp__mcp-tools-py__move_symbol`, `move_module`, `rename_symbol`, `list_symbols`, `find_references` |
| Git (read-only) | `mcp__mcp-workspace__git` |
| Get base branch | `mcp__mcp-workspace__get_base_branch` |
| Check file size | `mcp__mcp-workspace__check_file_size` |
| Check branch status | `mcp__mcp-workspace__check_branch_status` |
| List GitHub issues | `mcp__mcp-workspace__github_issue_list` |
| View GitHub issue | `mcp__mcp-workspace__github_issue_view` |
| View GitHub PR | `mcp__mcp-workspace__github_pr_view` |
| Search GitHub | `mcp__mcp-workspace__github_search` |

## Code quality checks

After making code changes, run:

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check
mcp__mcp-tools-py__run_mypy_check
```

All checks must pass before proceeding.

**Pytest:** always use `extra_args: ["-n", "auto"]` for parallel execution.

When debugging test failures, add `"-v", "-s", "--tb=short"` to extra_args.

## Git operations

**Prefer MCP tools** for read-only git operations: use `mcp__mcp-workspace__git` with the `command` parameter (log, diff, status, merge_base, show, branch, fetch, rev_parse, ls_tree, ls_files, ls_remote). These run without permission prompts.

**Compact diff:** `mcp__mcp-workspace__git` with command `"diff"` includes compact diff by default — detects moved code, collapses unchanged blocks. Use `compact=False` for raw output.

**Bash commands** for git operations that have no MCP equivalent:

```
git commit / git add
gh run view
mcp-coder gh-tool set-status <label>
```

**Status labels:** use `mcp-coder gh-tool set-status` to change issue workflow status — never use raw `gh issue edit` with label flags.

**Before every commit:** run `mcp__mcp-tools-py__run_format_code`, then stage and commit.

**Bash discipline:** no `cd` prefix. Don't chain approved with unapproved commands. Run them separately.

**Commit messages:** standard format, clear and descriptive. No attribution footers.

## Shared Libraries

This project uses **mcp-coder-utils** (`mcp-coder-utils` reference project) for shared utilities:

| Module | Import |
|--------|--------|
| Logging | `from mcp_coder_utils.log_utils import setup_logging, log_function_call` |

**Rules:**
- Browse the source via `mcp-coder-utils` reference project before reimplementing anything
- Never create local workarounds — file issues/feature requests at [mcp-coder-utils](https://github.com/MarcusJellinghaus/mcp-coder-utils) instead

## Writing style

Be concise. If one line works, don't use three.

## MCP server issues

Alert immediately if MCP tools are not accessible — this blocks all work.
