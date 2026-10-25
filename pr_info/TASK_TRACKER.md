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

### Step 1: Pure facts module — `ProtectionFacts`, `facts_from_classic`, `facts_from_rules`, `merge`, `source_label` ([step_1.md](./steps/step_1.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `RulesOutcome`, move `short_reason`, add `fetch_rules` ([step_2.md](./steps/step_2.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: Classic-only refactor into `_protection_result` / `_rows_from_facts` + `require_pull_request` row ([step_3.md](./steps/step_3.md))
- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: Wire rulesets fetch and classic/rules merge into `verify_github` ([step_4.md](./steps/step_4.md))
- [ ] Implementation (tests + production code)
- [ ] Quality checks: pylint, pytest, mypy — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review the full branch diff against `main`, address findings
- [ ] PR summary prepared (include the fine-grained token result from the `_ruleset_protection.py` docstring, or note that the token check is still open)
