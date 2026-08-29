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

### Step 1: Remove auto-added `is:` qualifiers (Cause A)

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation: strip injection assertions and delete `test_github_search_qualifier_injection` in `tests/github_operations/test_github_read_tools.py`, add the unmodified-query test, remove the auto-add block, footer and `import re` from `src/mcp_workspace/server.py`, update the docstring and `tests/LLM_Test.md:139`
- [x] Quality checks: pylint, pytest, mypy (plus vulture to confirm the removed `import re` leaves nothing flagged) — fix all issues
- [x] Commit message prepared

### Step 2: Build the full query string for `state` / `labels` / `assignee` (Cause B)

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation: rewrite `test_github_search_with_qualifiers` and add multi-label, special-character-label, state-only, qualifier-only and state-vocabulary tests, then build the complete query string inline in `github_search` with `state` validation and an updated docstring
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (message used in commit 117085d; `pr_info/.commit_message.txt` cannot be written — the MCP workspace tools refuse gitignored paths and no shell tool is available)

### Step 3: Live integration test

Details: [step_3.md](./steps/step_3.md)

- [x] Implementation: add one `@pytest.mark.github_integration` test making both live searches (qualifier-only and free-text-plus-qualifiers) with a runtime-discovered anchor issue — no production code
- [x] Quality checks: pylint, pytest, mypy — fix all issues; also run pytest with `markers=["github_integration"]` against the live API. Blocked across two earlier runs by an HTTP 422 (`Query must include 'is:issue' or 'is:pull-request'`) caused by production behaviour, not the test. Unblocked by [Step 4](#step-4-default-to-isissue-unblocks-step-3s-live-run), which adds the missing result-type token. All four now pass: pylint ✅, mypy ✅, 1577 unit tests ✅, live `github_integration` run ✅ (15 passed, 1 skipped)
- [x] Commit message prepared (`pr_info/.commit_message.txt` cannot be written — the MCP workspace tools refuse gitignored paths and no shell tool is available; message reproduced in the run output)

### Step 4: Default to `is:issue` (unblocks step 3's live run)

Details: [step_4.md](./steps/step_4.md)

- [x] Implementation: restore `import re` and add `is:issue` in `src/mcp_workspace/server.py` when the query names none of `is:issue` / `is:pr` / `is:pull-request`; update the docstring, the exact-query assertions in `tests/github_operations/test_github_read_tools.py`, two new parametrized tests, `tests/LLM_Test.md:139`, and the amended decisions in `pr_info/steps/summary.md`
- [x] Quality checks: pylint ✅, mypy ✅, 1577 unit tests ✅, live `markers=["github_integration"]` run ✅ (15 passed, 1 skipped)
- [x] Commit message prepared (`pr_info/.commit_message.txt` still cannot be written — `save_file` rejects it as gitignored and no shell tool is exposed in this session; message reproduced in the run output)
- [x] **Maintainer review:** this step reverses summary decision #3 and changes the tool's public default result type. It was implemented on the recommendation recorded twice in [step_3.md](./steps/step_3.md) rather than on an explicit instruction, because step 3 could not be completed otherwise. **Reviewed and accepted** — the `is:issue` default stands; the alternative (require an explicit type token) was rejected because it breaks every call site to defer a choice the caller cannot make better than the tool. Rationale recorded in "Open point for the maintainer — resolved" in [step_4.md](./steps/step_4.md). Re-verified on the current tree: pylint ✅, mypy ✅, 1577 unit tests ✅ (1 skipped)

### Step 5: CI rework — file-size and black failures from steps 3/4

No detail file: this is rework on the steps above, not new scope.

- [x] Implementation: `./tools/format_all.sh` and the file-size check were not run before committing the step 3/4 changes, so CI's `file-size` and `black` jobs both failed. `tests/github_operations/test_github_read_tools.py` had grown to 859 lines against the 750-line limit; split it along its existing `# github_search tests` banner into a new `tests/github_operations/test_github_search_tool.py` (the `github_search` unit tests plus the live `github_integration` test, with its own imports and a copy of the autouse `setup_server` fixture), leaving the `github_issue_view` / `github_issue_list` / `github_pr_view` tests behind. Not added to `.large-files-allowlist` — the allowlist's own guidance prefers refactoring, and this module had an obvious seam. Also collapsed the over-wrapped `stable = [...]` comprehension in the live test that black rejected.
- [x] Quality checks: black/isort ✅ (197 files unchanged on re-check), pylint ✅, mypy ✅, 1577 unit tests ✅ (1 skipped), file-size ✅ (all 311 files within 750 lines)
- [x] Commit message prepared

## Pull Request

- [x] PR review: address review feedback
- [ ] PR summary prepared
