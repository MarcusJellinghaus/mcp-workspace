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

### Step 1 — `server.py`: per-project default limit (global, setter, resolution, threading)

See [steps/step_1.md](./steps/step_1.md).

- [x] Implementation (tests + production code): add `_file_size_limit` global and `set_file_size_limit()` setter; change `check_file_size` signature/resolution/docstring; add `file_size_limit` param to `run_server` and call the setter; add tests in `tests/test_server.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — the message is captured in commit `3c36fa8` ("feat(workspace): add configurable file size limit"). The file `pr_info/.commit_message.txt` is gitignored; MCP `save_file` and `append_file` both refuse it (re-verified), and no shell/Write tool is available, so the message could not additionally be written to that path.

### Step 2 — `main.py`: `--file-size-limit` CLI flag, fail-fast validation, wiring

See [steps/step_2.md](./steps/step_2.md).

- [x] Implementation (tests + production code): add `--file-size-limit` arg (`type=int`, default `None`); `<= 0` validation in `main()`; pass `file_size_limit=args.file_size_limit` to `run_server`; add tests in `tests/test_reference_projects.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared — `pr_info/.commit_message.txt` is gitignored and MCP `save_file`/`append_file` refuse it (re-verified), with no shell/Write tool available, so the message is captured here instead:

  ```
  feat(workspace): add --file-size-limit CLI flag

  Add a --file-size-limit argument to main.py so operators can configure
  the default line limit used by the check_file_size MCP tool when
  max_lines is omitted.

  - parse_args() adds --file-size-limit (type=int, default None)
  - main() fails fast with exit code 1 when the value is <= 0
  - the value is threaded to run_server(file_size_limit=...)
  - tests cover parsing, non-integer rejection, <= 0 validation,
    pass-through, and backward-compatible default (None)
  ```

## Pull Request

- [ ] Address PR review feedback
- [ ] Write PR summary
