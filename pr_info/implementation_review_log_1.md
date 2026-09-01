# review-implementation review log 1

## Round 1 — 2026-09-01
**Findings**:
I'll start by loading the tool schemas I need.I'll gather context in parallel: knowledge base files, the issue, plan files, and the diff.The `main` ref isn't local. Let me find the right base ref and read the plan/knowledge-base files.Now the diff against `origin/main`, plus the remaining knowledge base and step files.The compact renderer collapsed the source diff. Let me get the implementation diff explicitly.Now let me verify consistency across the repo — hunting for surviving copies of the old lists.All old enumerations are gone. Now let me verify the checks actually pass.Checks pass. Let me verify one factual claim in the instructions text — whether reference projects are always local checkouts.All checks pass (pytest 2263 passed / 2 skipped, pylint, mypy, ruff clean). The diff contains real implementation changes, so the review proceeds.

`README.md:390` — medium — The quoted `usage` example is still a verbatim copy of the source literal in `src/mcp_workspace/server_reference_tools.py:74` with no automated guard; the issue's stated root cause was exactly this README copy drifting, and shrinking the string reduces the cost of drift without preventing it.

`tests/test_server_instructions.py:17` — low — `assert "\\" not in text and "/" not in text` is a brittle proxy for "no filesystem path": it also rejects legitimate slashes (URLs, `owner/repo`, `read/write`), so unrelated rewording of the instructions fails the test for a reason unrelated to the constraint it encodes.

`src/mcp_workspace/server.py:54` — low — "Answer questions about another repo from its reference project instead of asking the user" is unconditional, but the text ships in every session including servers with zero reference projects configured, prompting a pointless `get_reference_projects()` call.

`src/mcp_workspace/server_reference_tools.py:38` — low — Docstring summary still reads "Get available reference project names" while the payload is `{"name", "url"}` dicts; the adjacent `Returns:` line was corrected in this same diff but the summary retains the identical inaccuracy.

`README.md:235` — low — The per-tool table gains `search_reference_files` and `git` but the workspace `search_files` tool remains absent, so the table that step 3 designates as "the place where every tool is named" is still incomplete.
**Decisions**:
Verdict(decision='tasks', tasks=['Add a test that reads the usage example quoted in README.md:390 and asserts it matches the usage literal in src/mcp_workspace/server_reference_tools.py:74 verbatim, so the documented copy cannot silently drift from the source.', 'Replace the blanket `assert "\\\\" not in text and "/" not in text` in tests/test_server_instructions.py:17 with an assertion that targets actual filesystem paths (e.g. drive letters, absolute POSIX paths, or the configured vault/project root strings), so legitimate slashes such as `owner/repo` or URLs do not fail the test.', 'Fix the docstring summary at src/mcp_workspace/server_reference_tools.py:38 to describe the real payload (reference projects as `{"name", "url"}` entries) instead of "Get available reference project names", matching the `Returns:` line corrected in this diff.', 'Add the workspace `search_files` tool to the per-tool table at README.md:235 so the table names every tool as step 3 requires.'], escalate_reason=None)
**Changes**:
applied
