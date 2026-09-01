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

## Round 2 — 2026-09-01
**Findings**:
I'll gather context first.`src/mcp_workspace/server.py:52` — medium — Always-on instructions state unconditionally that a reference project's GitHub issues and pull requests are reachable, but a project configured without a URL (`url: null`) is rejected by the GitHub tools (`README.md:382`); the text gives no hint that GitHub access depends on the configured URL.
`src/mcp_workspace/server_reference_tools.py:47` — low — The docstring pointer restates the `usage` literal at line 76 verbatim (only the trailing period differs); the new drift test guards the README copy only, so this in-file duplicate — the root cause the issue targets — remains unguarded.
`tests/test_reference_projects_mcp_tools.py:79` — low — The README-drift test resolves `README.md` via `Path(__file__).parent.parent`, so it errors rather than skips when the suite runs outside a source checkout, and it lives in the MCP-tool behaviour class rather than with docs-consistency tests.
**Decisions**:
Verdict(decision='tasks', tasks=['Qualify the reference-project GitHub claim in the always-on instructions at src/mcp_workspace/server.py:52 so it states that issue and pull-request access requires the reference project to have a configured URL, matching the behaviour documented at README.md:382 where a `url: null` project is rejected by the GitHub tools.', 'Remove the verbatim restatement of the `usage` literal from the docstring at src/mcp_workspace/server_reference_tools.py:47 — have the docstring point at the literal defined at line 76 (or build the docstring text from it) instead of duplicating the string, so the in-file copy cannot drift the way the README copy did.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-09-01
**Findings**:
I'll gather context first.`src/mcp_workspace/server_reference_tools.py:76` — medium — No test asserts the `usage` string and docstring stay free of individual tool names (issue verification bullet 2); the drift the issue targets can silently reappear here, while only the instructions text and the README copy are guarded.

`tests/test_reference_projects_mcp_tools.py:74` — low — `test_readme_usage_example_matches_source` mutates the module global `_reference_projects` without restoring it and resolves `README.md` via `Path(__file__).parent.parent`, so it errors rather than skips outside a source checkout.

`src/mcp_workspace/server.py:54` — low — "Answer questions about another repo from its reference project instead of asking the user" ships unconditionally, including on servers with zero reference projects configured.

No `critical` or `high` findings. Pytest (2274 passed, 2 skipped), pylint, mypy and ruff all pass on the branch.
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
