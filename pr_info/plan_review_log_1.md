# review-plan review log 1

## Round 1 — 2026-09-29
**Findings**:
I'll gather context: knowledge base, the issue and its links, and the plan files.`pr_info/steps/step_3.md:4` — high — "no source change is expected" is wrong: the file's third parametrised test `test_unknown_reference_name_returns_error` (`test_github_write_tools_reference.py:143`) also consumes `_TOOL_CASES` and asserts the exact string `Error: Reference project 'nope' not found`; the new tools render that ValueError through `_api_error`, which appends `_ref_suffix`, so all three new cases fail

`pr_info/steps/step_2.md:85` — high — `_api_error` appends `_ref_suffix(reference_name)` to every caught exception, including the `_issue_manager()` reference-resolution ValueError, producing `Error: Reference project 'nope' not found in reference project 'nope'`; the manager must be resolved outside the suffix-appending path (or that error special-cased) to stay byte-consistent with the other issue tools

`pr_info/steps/step_2.md:73` — medium — `except Exception` contradicts approved Decision 16 (`(GithubException, ValueError)`) and turns genuine programming errors (AttributeError/TypeError on PyGithub objects) into caller-facing `Error: ...` strings instead of failing loudly

`pr_info/steps/summary.md:206` — medium — step 3 is ~7 lines of parametrised test data fully coupled to step 2's tools; planning principles say merge tiny/intertwined steps, so it belongs in step 2's commit

`pr_info/steps/step_1.md:154` — low — `_write_link` calls `repo.get_issue` three times (parent, child, refetched parent), but the test guidance only says "the returned parent is the refetched one"; specify the `side_effect` ordering so cases 1 and 2 are written against the real call sequence
**Decisions**:
Verdict(decision='tasks', tasks=["In pr_info/steps/step_2.md, resolve the issue manager via `_issue_manager()` outside the `_api_error` / `_ref_suffix` path, or special-case its reference-resolution ValueError. An unknown reference_name must return exactly `Error: Reference project 'nope' not found`, the same bytes as the other issue tools.", 'In pr_info/steps/step_2.md, replace `except Exception` with `except (GithubException, ValueError)` per approved Decision 16, so programming errors still raise.', "Remove the 'no source change is expected' claim from pr_info/steps/step_3.md:4. The plan must note that `test_unknown_reference_name_returns_error` (test_github_write_tools_reference.py:143) also runs on the new `_TOOL_CASES` entries and asserts the exact unknown-reference error string.", "Merge step 3's parametrised `_TOOL_CASES` test additions into step 2 so they land in the same commit. Update pr_info/steps/summary.md and renumber the steps.", 'In pr_info/steps/step_1.md, give the `repo.get_issue` mock `side_effect` order for the `_write_link` tests: parent, then child, then the refetched parent. Cases 1 and 2 should assert that the refetched parent is the one returned.'], escalate_reason=None)
**Changes**:
applied
