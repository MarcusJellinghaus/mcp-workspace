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

### Step 1: Foundation — module skeleton, helpers, exports, importlinter exception

See [step_1.md](./steps/step_1.md).

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: Tier 1 baseline checks — `git_binary`, `git_repo`, `user_identity`

See [step_2.md](./steps/step_2.md).

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Tier 1 signing detection — `signing_intent`, `signing_consistency`

See [step_3.md](./steps/step_3.md).

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 4: Tier 2 config-only checks — `signing_format`, `signing_key`

See [step_4.md](./steps/step_4.md).

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 5: Tier 2 binary checks — `signing_binary`, `signing_key_accessible`

See [step_5.md](./steps/step_5.md).

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 6: Tier 2 auxiliaries — `agent_reachable`, `allowed_signers`, `verify_head`

See [step_6.md](./steps/step_6.md).

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

### Step 7: Tier 3 opt-in deep probe — `actual_signature`

See [step_7.md](./steps/step_7.md).

- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review
- [ ] PR summary
