# review-plan review log 1

## Round 1 — 2026-11-24
**Findings**:
Plan files and issue read; now checking README, `verify_github`, and the mcp_coder test names against the plan.Verifying the `SectionBuilder` API the plan's step 3 relies on, plus vulture setup.Status: plan reviewed against issue #409, knowledge base, current `main.py`/`.importlinter`/`tach.toml`, mcp_coder sources and `verify_render`; no blocking gaps found.

pr_info/steps/step_1.md:64 — low — `format_file_access_section` sets `wrap=True` on every row, but the issue asks for it only on the invalid row. FILE ACCESS has no byte-identity requirement, so output is unaffected; set `wrap` only for the `ok is False` row to match the issue.
pr_info/steps/step_4.md:87 — low — When `--project-dir` is omitted and cwd is not a usable directory, the error reads `must be an existing directory: None`. Show the resolved candidate (`args.project_dir or str(Path.cwd())`) in the message instead.
pr_info/steps/step_4.md:130 — low — The `--log-level debug` test has no observable assertion. Specify it, e.g. `setup_logging` called with `"DEBUG"` (patch `mcp_workspace.main.setup_logging`).
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_1.md:64 — in `format_file_access_section`, set `wrap=True` only on the row where `ok is False` (the invalid row), as the issue specifies, rather than on every row.', 'pr_info/steps/step_4.md:87 — when `--project-dir` is omitted and the resolved directory is not usable, build the error message from the resolved candidate (`args.project_dir or str(Path.cwd())`) so it never prints `must be an existing directory: None`; add or adjust the corresponding test to assert the cwd path appears in the message.', 'pr_info/steps/step_4.md:130 — give the `--log-level debug` test an observable assertion: patch `mcp_workspace.main.setup_logging` and assert it is called with `"DEBUG"`.'], escalate_reason=None)
**Changes**:
applied
