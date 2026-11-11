# review-plan review log 1

## Round 1 — 2026-11-11
**Findings**:
Reading the remaining plan steps and the library code they depend on, so I can check the plan against what the code actually does.Checking the `.importlinter` contracts and the toolset tests the plan depends on.Last check: confirming the docs tables that step 14 edits exist.pr_info/steps/step_9.md:88 — medium — The unit tests patch library functions where they are defined (e.g. `mcp_workspace.git_operations.branches.switch_branch`). `_git_write_helpers.py` imports them at top level, so after `from … import fn` the patch has no effect and the tests run real git. Patch `mcp_workspace.toolset._git_write_helpers.<fn>` instead. The same "patch library" wording in step_10.md:61, step_11.md:68, step_12.md:56 and step_13.md:45 inherits this.
pr_info/steps/step_9.md:62 — medium — `git_branch(name, create=False, base=...)` checks `base` and then ignores it without saying so. Return `Error: base requires create=True` so a misused argument is reported, not dropped. Add a unit test for it.
pr_info/steps/summary.md:67 — medium — The bare-origin plus real-clone fixtures (`origin_clone` / `make_clone`) only arrive in step 9, in `tests/toolset/conftest.py`. Steps 2, 3 and 5 need the same setup and each build it separately (step_2.md:74, step_3.md:62, step_5.md:59), so the code is duplicated. Introduce the fixtures in step 2 in `tests/conftest.py`, which is the promotion the issue suggests, and reuse them everywhere.
pr_info/steps/step_2.md:80 — low — Step 2 is the first to test the fresh-clone "no reflog" behaviour, but the stop-if-a-reflog-exists check is only in step_13.md:55. Put the same `.blocked.txt` check in step 2, where that assumption is first relied on.
pr_info/steps/step_11.md:48 — low — `commit_paths` also returns `nothing_to_commit` for a path that is neither tracked nor on disk, e.g. a typo. Its `commits.py` docstring says so. The tool would then report `Nothing to commit` and hide the bad path. Name the given paths in that message, or check that they exist first.
pr_info/steps/step_14.md:15 — low — Two `docs/LIBRARY_USE.md` notes are not updated:
- The TLS/network note (line 53) still says only `workspace.github` and `workspace.checks` need TLS or network. `workspace.git` now pushes, runs `ls-remote`, and `git_branch_delete` calls the GitHub API.
- The locks note (line 54) does not mention the new `git_write_lock`, which, like the file locks, belongs to one `tool_specs()` call.
**Decisions**:
Verdict(decision='tasks', tasks=['In step_9.md (around line 88), make the unit tests patch the names where `_git_write_helpers.py` imports them, e.g. `mcp_workspace.toolset._git_write_helpers.switch_branch`. Do not patch where the functions are defined in `mcp_workspace.git_operations.*`. Make the same fix to the patch wording in step_10.md:61, step_11.md:68, step_12.md:56 and step_13.md:45.', 'In step_9.md (around line 62), make `git_branch` return `Error: base requires create=True` when `base` is given with `create=False`, instead of ignoring it. Add a unit test for this case.', "Move the `origin_clone` / `make_clone` fixtures (a bare origin plus a real clone) from step 9's `tests/toolset/conftest.py` into `tests/conftest.py`, and introduce them in step 2. Change step_2.md:74, step_3.md:62, step_5.md:59 and step 9 to reuse them instead of each building its own setup.", "In step_11.md (around line 48), when `commit_paths` returns `nothing_to_commit`, make the tool's `Nothing to commit` message list the given paths, so a mistyped or missing path shows up.", 'In step_14.md, also update two notes in `docs/LIBRARY_USE.md`. Line 53, the TLS/network note: add `workspace.git`, because it now pushes, runs `ls-remote`, and `git_branch_delete` calls the GitHub API. Line 54, the locks note: mention the new `git_write_lock`, which belongs to one `tool_specs()` call, like the file locks.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-11
**Findings**:
Now the steps.Plan files are read; now checking the code the plan relies on (commit, branch-query and GitHub helpers) before writing findings.Cross-checking step 15's CLAUDE.md edit against the skills/settings it would affect.pr_info/steps/step_15.md:42 — medium — Step 15 removes `commit` and `push` from the Bash list but says nothing about the sentence at `.claude/CLAUDE.md:108` ("Skills that instruct bash commands (e.g. `git commit`) must also use Bash"). This repo's synced `.claude/skills/commit_push/SKILL.md`, `.claude/skills/rebase/SKILL.md` and `.claude/agents/commit-pusher.md` still run Bash `git commit` / `git push` until mcp_coder#1415 syncs. The step should say to keep that exception, so those skills don't conflict with the MCP-only rule.
pr_info/steps/step_11.md:46 — low — If `stage_paths` fails partway, the files staged by earlier chunks stay staged. `_run_chunked` leaves earlier chunks staged, and the plan returns `Error` without unstaging them. Call `unstage_paths(staged)` on a staging failure too, as on a commit failure.
pr_info/steps/step_9.md:68 — low — `short(resolve_commit(project_dir, 'HEAD'))` passes a `str | None` into `short(sha: str)`, which mypy will reject. Handle the None case, or take the SHA from the create result.
**Decisions**:
Verdict(decision='tasks', tasks=['In step_15.md (around line 42), say that the step keeps the exception at `.claude/CLAUDE.md:108` ("Skills that instruct bash commands (e.g. `git commit`) must also use Bash") while removing `commit`/`push` from the Bash list. The synced `commit_push` and `rebase` skills and the `commit-pusher` agent still run Bash `git commit` / `git push` until mcp_coder#1415 syncs.', 'In step_11.md (around line 46), when `stage_paths` fails partway, call `unstage_paths` on the paths already staged before returning the Error, as the commit-failure path does. Add a unit test for a staging failure partway through.', "In step_9.md (around line 68), handle `resolve_commit(project_dir, 'HEAD')` returning None before calling `short(...)`, or take the SHA from the create result instead, so that mypy passes."], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-11-11
**Findings**:
Now the step files.Plan files are read; now checking a few library details the plan relies on (`_handle_github_errors`, `WorkspaceContext`, snapshot test, import test).Last check: confirming `scrub_credentials` is where step 1 imports it from.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
