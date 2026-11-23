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

### Step 1: `.git` refusal uses `normalize_path`'s message — [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy) — fix all issues
- [x] Commit message prepared

### Step 2: Remove `check_path_not_gitignored` — [step_2.md](./steps/step_2.md)

- [x] Implementation (precondition check + removal + docs)
- [x] Quality checks (pylint, pytest, mypy, vulture) — fix all issues
- [x] Commit message prepared

### Step 3: Gitignore refusal hint and invalid-file note — [step_3.md](./steps/step_3.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 4: Raises clauses in tool descriptions — [step_4.md](./steps/step_4.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 5: Server instructions sentence — [step_5.md](./steps/step_5.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 6: Search `warning` key — [step_6.md](./steps/step_6.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 7: Workspace label ` (read-only, not committed)` — [step_7.md](./steps/step_7.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 8: Reference label ` (not committed)` — [step_8.md](./steps/step_8.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

### Step 9: `verify_file_access` and startup warning — [step_9.md](./steps/step_9.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, vulture, lint-imports, tach) — fix all issues
- [ ] Commit message prepared

### Step 10: Docs — rules-file and missing-path notes — [step_10.md](./steps/step_10.md)

- [ ] Implementation (docs + final acceptance check)
- [ ] Quality checks (pylint, pytest, mypy) — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main` and the issue's acceptance list
- [ ] PR summary prepared
