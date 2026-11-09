# review-plan review log 1

## Round 1 — 2026-11-09
**Findings**:
Read the issue, knowledge base and all 7 plan steps; now checking a few codebase facts the plan depends on.Codebase checks mostly done; reading `github_label_list` and the layered contract before writing findings.pr_info/steps/step_2.md:18 — high — Moving the autouse `cache_dir` fixture up to `tests/github_operations/conftest.py` breaks `tests/github_operations/issues/test_cache_io.py:85` (`test_get_cache_file_path_basic`). That test builds its expected path from the real, unpatched `get_user_app_data_dir("mcp_coder")`. Once the fixture is autouse at this level, `_get_cache_file_path` returns a path under `tmp_path`, so the paths no longer match. The step doesn't list this test, so the step can't finish with checks green unless the plan adds it: compare against the `cache_dir` fixture, as `caching/test_store.py:30` does.
pr_info/steps/step_5.md:26 — medium — The new `STATUS_LABEL_PREFIX` / `is_status_label` in `issues/status.py` copies the existing `server.py` `_STATUS_LABEL_PREFIX` plus the casefold check in `_check_labels`. Step 6 edits that code (`pr_info/steps/step_6.md:61-65`) but keeps both copies. Step 6 should have `_check_labels` use `is_status_label` (lazy import) and drop `_STATUS_LABEL_PREFIX`, so the rule for what counts as a status label lives in one place.
pr_info/steps/step_6.md:25 — low — Adding `github_issue_set_status` to `_TOOL_CASES` also needs a matching entry in `_TOOL_IDS` (`test_github_write_tools_reference.py:121-129`). It also needs kwargs that include the required `number` and `status`, e.g. `{"number": 42, "status": "status-01:created"}`. With `{}` the call fails with a `TypeError`.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_2.md, add tests/github_operations/issues/test_cache_io.py::test_get_cache_file_path_basic to the step\'s changes. Rewrite it so the expected path comes from the `cache_dir` fixture, the way caching/test_store.py:30 does, instead of from the unpatched get_user_app_data_dir("mcp_coder"). It must still pass once the autouse cache_dir fixture moves to tests/github_operations/conftest.py.', 'In pr_info/steps/step_6.md (around lines 61-65), change server.py `_check_labels` to call `is_status_label` from issues/status.py through a lazy import. Then delete the duplicated `_STATUS_LABEL_PREFIX` from server.py, so the status-label rule lives only in issues/status.py.', 'In pr_info/steps/step_6.md (around line 25), when adding github_issue_set_status to `_TOOL_CASES` in test_github_write_tools_reference.py, add a matching entry to `_TOOL_IDS` (lines 121-129). Give the case kwargs that include the required arguments, e.g. {"number": 42, "status": "status-01:created"}, instead of {}.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-09
**Findings**:
Reviewing plan against code: checking `issue_to_data`, import-linter contracts, and `github_label_list`.I found one substantive problem in the plan, at medium severity:

pr_info/steps/step_1.md:62 — medium — `_valid_entry` only checks that each cached label has a str `name`. Both consumers also index `description` (step 2's search filter, step 5's invalid-status list), and `github_label_list` also indexes `color`. The issue says the `.labels.json` file is shared with mcp-coder, so an entry missing one of these fields would make both tools return an `Error: 'description'`-style `KeyError` instead of refetching. Require all four `LabelData` fields to be str in `_valid_entry`, and add a step-1 test where an entry lacking `description` counts as a miss.
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_1.md (around line 62), make `_valid_entry` require all four LabelData fields (name, color, description, plus the remaining field) to be present and of type str. An entry that fails this should count as a cache miss and trigger a refetch, so it can't raise a KeyError in the step-2 search filter, the step-5 invalid-status list, or github_label_list. Add a step-1 test where a cached entry without `description` is treated as a miss."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-11-09
**Findings**:
Round 3 plan review: I've read the issue, the plan files and the import contracts. Now I'm checking the code the plan relies on (`rate_limit_guard`, test fixtures, `labels_mixin`).Still reviewing: checking whether the existing `github_label_list` reference tests survive the change to the cache.`pr_info/steps/step_2.md:83` — medium — The step only lists the `TestGithubLabelList` assertions to update. `tests/github_operations/test_github_write_tools_reference.py:220` (`test_no_labels_names_reference_project`) checks for exact equality: `result == "No labels found in reference project 'sibling'."`. Once step 2 appends the cache footer as the last line, that test fails. Add it to step 2's test adjustments: check `result.splitlines()[0]` and that the last line starts with `Label cache last updated `.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
