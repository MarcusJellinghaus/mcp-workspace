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

### Step 1: `run_git_timed` names the command after leading `-c` pairs
See [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 2: `git log` pickaxe flags
See [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 3: `read_content` / `decode_lines` — the read line loop on bytes
See [step_3.md](./steps/step_3.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 4: `search_paths` — search engine on an injected file list and reader
See [step_4.md](./steps/step_4.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 5: `ref_relative_path` — lexical paths at the ref
See [step_5.md](./steps/step_5.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 6: `ref_snapshot` — reading at `origin/<default>` via GitPython
See [step_6.md](./steps/step_6.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy, lint-imports) — fix all issues
- [x] Commit message prepared

### Step 7: `origin_fetch` — fetch with retry
See [step_7.md](./steps/step_7.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy, lint-imports) — fix all issues
- [x] Commit message prepared

### Step 8: Clone state moves into `WorkspaceContext`; `ensure_available` reports a clone
See [step_8.md](./steps/step_8.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy, vulture) — fix all issues
- [x] Commit message prepared

### Step 9: `reference_fetch_interval_minutes` setting (tool_specs, server, CLI)
See [step_9.md](./steps/step_9.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy, vulture) — fix all issues
- [x] Commit message prepared

### Step 10: Throttled auto-fetch + notes; `git` tool uses it
See [step_10.md](./steps/step_10.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy, lint-imports, vulture, serial performance tests) — fix all issues
- [x] Commit message prepared

### Step 11: Read and list read at the ref (`_reference_call`, fallback, notes)
See [step_11.md](./steps/step_11.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, lint-imports, vulture, serial performance tests) — fix all issues
- [ ] Commit message prepared

### Step 12: Search reads at the ref (`search_paths` with a blob reader, `freshness`, `skipped_files`)
See [step_12.md](./steps/step_12.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, lint-imports, vulture, serial performance tests) — fix all issues
- [ ] Commit message prepared

### Step 13: Tool docstrings, server instructions, description tests
See [step_13.md](./steps/step_13.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 14: Documentation
See [step_14.md](./steps/step_14.md)

- [ ] Implementation (docs; leftover-statement search per step)
- [ ] Quality checks (pytest) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main` and fix any findings
- [ ] PR summary prepared
