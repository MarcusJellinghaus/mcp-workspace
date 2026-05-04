# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: Use `mcp_coder_utils` Path Helper in `config.py`

See [step_1.md](./steps/step_1.md) for details.

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 2: Runtime Strings Use the `mcp_coder_utils` Helper

See [step_2.md](./steps/step_2.md) for details. Note: implementation uses
`get_user_app_data_dir("mcp_coder") / "config.toml"` computed at message-build
time, not the originally-planned `get_user_config_path()`.

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 3: Docstrings (no-op per updated issue Decisions)

Per issue #184 Decisions: *"Keep literal `~/.mcp_coder/config.toml` text
(correct on every platform under mcp-coder-utils#31)"*. Existing docstrings
are already in the neutral form, no changes needed.

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: Adopt helper in `issues/cache.py` (added per issue #184)

Replaced `Path.home() / ".mcp_coder" / "coordinator_cache"` with
`get_user_app_data_dir("mcp_coder") / "coordinator_cache"` and updated
the matching test assertion in `tests/github_operations/test_issue_cache.py`.

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: `mcp-coder-utils` dep in pyproject.toml

Switched the dep from `mcp-coder-utils>=0.1.0` to a git URL pointing at
HEAD because the `user_app_data` helper hasn't shipped in any tagged
release yet (latest is 0.1.4). When mcp-coder-utils 0.1.5+ ships with
the helper, revert this back to a normal version pin like
`mcp-coder-utils>=0.1.5`.

- [x] Dep updated (interim git URL — revert to version pin after 0.1.5 ships)

## Pull Request

- [ ] PR review
- [ ] PR summary
