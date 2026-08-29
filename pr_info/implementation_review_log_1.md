# review-implementation review log 1

## Round 1 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context in parallel.I'll gather context in parallel: knowledge base, issue, plan files, and the diff.Issue is self-contained. Now the knowledge base, plan, and diff.Concerns resolved: `list_issues` defaults to `include_pull_requests=False`, so the live-test anchor is always a real issue. Let me verify the checks actually pass on this tree.All three checks pass on the current tree (1577 passed / 1 skipped, pylint clean, mypy clean). The diff contains real implementation changes in `src/mcp_workspace/server.py`, so the review proceeds.

`src/mcp_workspace/server.py:783` — medium — The `is:issue` default reverses issue #254's explicitly recorded decision ("Default `is:` qualifier after the fix | None") and changes `github_search`'s public default result type from "issues and PRs" to "issues only". The live-422 evidence in `pr_info/steps/step_3.md` is convincing, but step_4.md resolves its own "Open point for the maintainer" without maintainer sign-off, and issue #254's decision table was never amended — only `summary.md` was.

`tests/github_operations/test_github_search_tool.py:392` — medium — The live `github_integration` test only exercises the `is:issue` default path (`query=""`) plus label/state. The newly added suppression spellings `is:pr` and `is:pull-request` are mock-only, so if GitHub's endpoint rejects `is:pr` no test catches it — the same mocked-tests-can't-prove-syntax gap the issue was filed about.

`src/mcp_workspace/server.py:788` — low — Label values are wrapped in double quotes with no escaping of an embedded `"`. A label containing a quote emits a malformed qualifier and GitHub silently returns wrong results — the exact failure mode this issue fixes.

`src/mcp_workspace/server.py:776` — low — `state` validation runs after `manager._get_repository()`, so an invalid state still costs a network round-trip; the test docstring at `tests/github_operations/test_github_search_tool.py:210` claims it "fails loudly before any API call", which is inaccurate.

`tests/github_operations/test_github_search_tool.py:398` — low — `set_project_dir(repo_root)` mutates module-global server state and is never restored; the autouse fixture only resets it for tests within this module, not for other modules sharing the same xdist worker.

`tests/github_operations/test_github_search_tool.py:415` — low — Anchor selection depends on `list_issues` returning newest-first, an ordering the API does not guarantee. The oldest-plus-`order="asc"` pairing exists to keep the anchor inside the `max_results=100` cap, so a change in that ordering makes the test flaky on labels with many matches.

`src/mcp_workspace/server.py:758` — low — The `labels` docstring ("Filter by label names") does not state that multiple labels are ANDed, which is what `label:"a" label:"b"` means to GitHub; a caller expecting OR gets silently narrower results.
**Decisions**:
Verdict(decision='tasks', tasks=["Document the `is:issue` default deviation from issue #254's decision table: amend the issue's recorded decision (or add an explicit note in pr_info/steps/summary.md and the `github_search` docstring) stating that the default `is:` qualifier is `is:issue` rather than `None`, citing the live 422 evidence from step_3.md as the reason. Do not silently leave the decision table contradicting the implementation.", 'Extend the live `github_integration` test in tests/github_operations/test_github_search_tool.py to exercise the `is:pr` and `is:pull-request` suppression spellings against the real endpoint, not just the `is:issue` default path, so a rejected qualifier syntax is caught by a test rather than at runtime.', 'In src/mcp_workspace/server.py:788, escape embedded double quotes in label values before wrapping them in `label:"..."` (or reject labels containing quotes with a clear error), and add a unit test covering a label containing a `"` character.', "In src/mcp_workspace/server.py:776, move the `state` validation ahead of `manager._get_repository()` so an invalid state fails before any network round-trip, matching the docstring claim at tests/github_operations/test_github_search_tool.py:210 that it 'fails loudly before any API call'.", 'In tests/github_operations/test_github_search_tool.py:398, restore the previous project-dir value after `set_project_dir(repo_root)` (e.g. save-and-restore in a fixture teardown) so the module-global server state is not leaked to other test modules sharing an xdist worker.', 'In tests/github_operations/test_github_search_tool.py:415, stop relying on `list_issues` returning newest-first for anchor selection; select the anchor deterministically (e.g. explicitly sort the returned issues by number, or request an explicit ordering) so the test does not go flaky on labels with many matches.', 'In the `labels` parameter docstring at src/mcp_workspace/server.py:758, state explicitly that multiple labels are ANDed (`label:"a" label:"b"`), so callers do not assume OR semantics and silently get narrower results.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-08-28
**Findings**:
I'll start by loading the tools I need and gathering context.`src/mcp_workspace/server.py:782` — medium — The result-type detection regex only recognises `is:issue`/`is:pr`/`is:pull-request`; GitHub's equivalent `type:issue`/`type:pr` spelling is not matched, so `github_search(query="fix type:pr")` gets `is:issue` prepended and silently returns nothing — the same silent-wrong-answer failure mode issue #254 fixes.

`tests/LLM_Test.md:142` — medium — Line 139 was updated to `is:issue` default but steps 5-6 still say "Pick a closed PR number from step 2" and call `github_pr_view`; step 2 can no longer return a PR, so the manual live check for `github_pr_view` is now permanently unrunnable.

`tests/github_operations/test_github_search_tool.py:283` — low — The `if not line.startswith("(")` filter in `test_github_search_issue_vs_pr_indicator` existed only to strip the removed `(auto-added: ...)` footer; `format_search_results` emits no `(`-prefixed line and `github_search` caps `items` before formatting, so it is dead code left by this change.

`src/mcp_workspace/server.py:787` — low — An inline state qualifier in `query` (e.g. `"bug is:closed"`) combined with `state="open"` emits both `is:closed` and `is:open`, which GitHub resolves to an empty set with no warning; no validation or documentation covers the conflict.
**Decisions**:
Verdict(decision='tasks', tasks=["In src/mcp_workspace/server.py:782, extend the result-type detection regex to also recognise GitHub's `type:issue` / `type:pr` / `type:pull-request` spellings, so a caller-supplied `type:pr` suppresses the `is:issue` default instead of being silently contradicted; add unit tests covering `type:pr` and `type:issue` in the query.", "Update tests/LLM_Test.md steps 5-6 so the `github_pr_view` manual check is runnable again under the `is:issue` default: have the step obtain a closed PR number via an explicit PR search (e.g. a query containing `is:pr`) rather than reusing step 2's now issue-only results.", 'Remove the dead `if not line.startswith("(")` filter in `test_github_search_issue_vs_pr_indicator` at tests/github_operations/test_github_search_tool.py:283, since `format_search_results` no longer emits any `(`-prefixed footer line.', 'Handle the state-qualifier conflict in src/mcp_workspace/server.py:787: detect an inline state qualifier (`is:open`/`is:closed`/`state:open`/`state:closed`) in `query` and skip appending the `state` parameter\'s qualifier — mirroring the existing `is:issue` suppression — and document this precedence in the `state` docstring; add a unit test for `query="bug is:closed"` with `state="open"`.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-08-28
**Findings**:
I'll gather context first.`src/mcp_workspace/server.py:788` — high — The result-type suppression regex accepts `type:issue`/`type:pr`/`type:pull-request`, but nothing verifies GitHub's `/search/issues` treats a `type:` token as satisfying its result-type gate — the 422 quoted in `pr_info/steps/step_3.md` names only `is:issue` and `is:pull-request`. If it does not, `github_search(query="fix type:pr")` suppresses `is:issue` and errors with a 422; the live parametrized test at `tests/github_operations/test_github_search_tool.py:544` covers only `is:pr` and `is:pull-request`, so this path is mock-only — the exact "unverified syntax ships broken" gap issue #254 exists to close.

`src/mcp_workspace/server.py:750` — high — The docstring advertises the `type:` spellings as equivalent to `is:` for suppressing the default, promising a capability that no live test exercises (see `server.py:788`); a caller following the docstring gets a runtime 422 if GitHub's gate rejects `type:`.
**Decisions**:
Verdict(decision='tasks', tasks=["Verify the `type:` result-type spellings against the live GitHub `/search/issues` endpoint: extend the live `github_integration` parametrized test at tests/github_operations/test_github_search_tool.py:544 to cover `type:issue`, `type:pr`, and `type:pull-request` in addition to `is:pr`/`is:pull-request`. If GitHub's result-type gate rejects `type:` with a 422, remove `type:` from the suppression regex at src/mcp_workspace/server.py:788 so those queries keep getting the `is:issue` default instead of failing.", 'Align the `github_search` docstring at src/mcp_workspace/server.py:750 with whatever the live test proves: keep the `type:` spellings documented only if the live test confirms GitHub accepts them as satisfying the result-type gate, otherwise drop them from the docstring so callers are not directed at a syntax that returns a runtime 422.'], escalate_reason=None)
**Changes**:
applied

## Round 4 — 2026-08-28
**Findings**:
I'll start by loading the tool schemas I need.I'll gather context in parallel: knowledge base files, the issue, plan files, and the branch diff.`src/mcp_workspace/server.py:801` — high — The inline-state regex `(?:is|state):(?:open|closed)` treats a caller's `state:open`/`state:closed` as a valid state qualifier and therefore *suppresses* the `is:open`/`is:closed` the `state` parameter would emit; `state:` is unverified syntax by this PR's own decision table ("`is:open` is certain syntax; `state:open` is probable but unverified"), so `github_search(query="bug state:closed", state="open")` can drop the only reliable state filter and silently return unfiltered results — the exact failure mode #254 fixes. Coverage is mock-only (`tests/github_operations/test_github_search_tool.py:219`); the live parametrized test at `tests/github_operations/test_github_search_tool.py:561` covers only `is:pr`/`is:pull-request`/`type:pr`/`type:issue`, not `state:`.

`src/mcp_workspace/server.py:761` — high — The `state` docstring advertises `state:open`/`state:closed` as inline spellings that win over the `state` parameter, directing callers at a syntax no live test proves GitHub honors (see `server.py:801`); either live-verify it or restrict both the regex and the docstring to `is:open`/`is:closed`.
**Decisions**:
Verdict(decision='tasks', tasks=["Live-verify or remove the `state:` inline spelling in the state-suppression regex at src/mcp_workspace/server.py:801: extend the live `github_integration` parametrized test at tests/github_operations/test_github_search_tool.py:561 to cover `state:open`/`state:closed` against the real `/search/issues` endpoint. If GitHub does not honor `state:` as a state filter, narrow the regex to `is:(?:open|closed)` only, so a caller's unverified `state:closed` no longer suppresses the reliable `is:` qualifier emitted by the `state` parameter.", 'Align the `state` docstring at src/mcp_workspace/server.py:761 with the verified behavior: keep `state:open`/`state:closed` documented as precedence-winning inline spellings only if the live test confirms GitHub honors them, otherwise document only `is:open`/`is:closed` so callers are not directed at a syntax that silently drops state filtering.'], escalate_reason=None)
**Changes**:
applied

## Round 5 — 2026-08-28
**Findings**:
I'll gather context first.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
rebase-needed
**Escalate reason**: rebase
