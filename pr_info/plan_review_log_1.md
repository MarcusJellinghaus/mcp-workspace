# review-plan review log 1

## Round 1 — 2026-09-29
**Findings**:
I'll gather context first.`pr_info/steps/step_1.md:106` — medium — Test-cleanup target misrouted: `tests/file_tools/test_search.py` contains no `_discover_files` mocks (its only patch is `normalize_path` at line 604, load-bearing). The separator-dodging mocks the issue's Decisions table calls for dropping are in `tests/file_tools/test_directory_utils.py` (`test_list_files_basic:264`, `test_list_files_with_gitignore:306`), so that acceptance item would be silently skipped.

`pr_info/steps/step_1.md:17` — medium — Same misattribution in the WHERE table; `tests/file_tools/test_directory_utils.py` (row at line 15) is where the mock removal belongs.

`pr_info/steps/step_4.md:59` — medium — Fixture spec omits a file exceeding the line threshold, so the `check_file_size` parameter is vacuous: `render_output` emits paths only for violations or stale allowlist entries. Require a nested over-limit file (or `max_lines=0`) for that param to guard anything.

`pr_info/steps/summary.md:65` — medium — Deviation from the issue's Decisions table (`_build_tree`'s `replace` kept, unmatched-prefix warning dropped) is well reasoned and correctly flagged, but it leaves two issue items unmet as written: the "workarounds dispositioned as listed in `## Sites`" acceptance bullet and the "Unstripped-prefix mismatch → log a warning" decision. Needs explicit ratification before step 1 is implemented.

`pr_info/steps/summary.md:154` — low — `tests/test_reference_projects_mcp_tools.py` is listed as modified but no step touches it; step 4 uses `tests/test_reference_search_mcp_tools.py` as its fixture pattern source.

`pr_info/steps/summary.md:139` — low — Says `server.py` gets "four tool docstrings" while `pr_info/steps/step_5.md:12` assigns it two (`list_directory`, `search_files`) and the other two to `server_reference_tools.py`.

`pr_info/steps/step_4.md:90` — low — "Verify by stashing step 1 locally" is a manual verification step and is impossible once steps 1–3 are committed; keep only the automated fallback (asserting the helper flags a backslashed sample).
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_1.md (WHERE table row at line 15 and cleanup item at line 106), retarget the mock-removal work from tests/file_tools/test_search.py to tests/file_tools/test_directory_utils.py, naming the separator-dodging _discover_files mocks at test_list_files_basic:264 and test_list_files_with_gitignore:306; leave the load-bearing normalize_path patch in test_search.py:604 alone.', 'In pr_info/steps/step_4.md:59, extend the fixture spec so the check_file_size parameter actually exercises path output: add a nested file that exceeds the line threshold (or set max_lines=0), since render_output only emits paths for violations or stale allowlist entries.', 'Reconcile pr_info/steps/summary.md:139 with pr_info/steps/step_5.md:12 — summary claims four tool docstrings in server.py; step 5 assigns two to server.py (list_directory, search_files) and two to server_reference_tools.py. Fix the summary to match.', 'Drop the "stash step 1 locally" manual verification from pr_info/steps/step_4.md:90 (impossible once steps 1-3 are committed) and keep only the automated fallback asserting the helper flags a backslashed sample.', 'In pr_info/steps/summary.md, remove tests/test_reference_projects_mcp_tools.py from the modified-files list or assign it to a step; step 4 uses tests/test_reference_search_mcp_tools.py as its fixture pattern source.'], escalate_reason=None)
**Changes**:
applied
