# Step 3 — Dual-Path Docstring Updates

## LLM Prompt

> Read `pr_info/steps/summary.md` and the work done in `pr_info/steps/step_1.md`
> and `pr_info/steps/step_2.md`, then implement **Step 3** as defined in
> `pr_info/steps/step_3.md`. Replace the single-path docstring text in 9
> files with the dual-path form. This is a mechanical text replacement —
> no logic changes. After implementation, run
> `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with the recommended `-n auto`
> and integration markers excluded), and
> `mcp__mcp-tools-py__run_mypy_check`. Run
> `mcp__mcp-tools-py__run_format_code`, then make exactly one commit for
> this step.

## WHERE — Class Docstrings (production code, 5 sites)

| File | Approx. line |
|------|--------------|
| `src/mcp_workspace/github_operations/base_manager.py` | 138 |
| `src/mcp_workspace/github_operations/pr_manager.py` | 72 |
| `src/mcp_workspace/github_operations/ci_results_manager.py` | 131 |
| `src/mcp_workspace/github_operations/issues/branch_manager.py` | 25 |
| `src/mcp_workspace/github_operations/issues/manager.py` | 33 |

### Replacement (class docstrings)

**Find:**

```
Requires GitHub token in config file (~/.mcp_coder/config.toml):
```

**Replace with:**

```
Requires GitHub token in user config file
(~/.mcp_coder/config.toml on Windows, ~/.config/mcp_coder/config.toml on Linux/macOS):
```

## WHERE — Test Module Docstrings (4 sites)

| File | Approx. line |
|------|--------------|
| `tests/github_operations/test_github_integration_smoke.py` | 12 |
| `tests/github_operations/test_github_utils.py` | 9 |
| `tests/github_operations/test_issue_branch_manager_integration.py` | 9 |
| `tests/github_operations/test_issue_manager_integration.py` | 9 |

### Replacement (test docstrings)

**Find:**

```
Config File Alternative (~/.mcp_coder/config.toml):
```

**Replace with:**

```
Config File Alternative
(~/.mcp_coder/config.toml on Windows, ~/.config/mcp_coder/config.toml on Linux/macOS):
```

## WHAT

No code, no signatures, no imports — pure text replacement in module/class
docstrings. The remainder of each docstring (the `[github]` TOML block,
scope notes, "Note: Tests will be skipped..." line) stays unchanged.

## HOW (Integration Points)

- Use `mcp__mcp-workspace__edit_file` per file. Each find string is unique
  within its file, so a normal (non-`replace_all`) edit suffices.
- Do not modify the surrounding TOML example block.
- After all 9 edits, run the **comprehensive repo-wide grep gate**:
  `~/.mcp_coder/config.toml` should appear ONLY inside the dual-path
  sentences that include `on Windows`. There must be no remaining
  single-path occurrences in either runtime code or docstrings.

## ALGORITHM

```
for each of the 9 files:
    open file
    locate the single-path sentence
    replace with the dual-path sentence
    save

repo-wide grep gate:
    every match of "~/.mcp_coder/config.toml" must be on a line that also
    contains "on Windows" (i.e. it is part of a dual-path docstring).
```

## DATA

No data structures touched. No tests added or modified.

## Tests

None required — docstrings are documentation only and have no runtime
effect. The standard pylint / pytest / mypy verification confirms nothing
broke.

## Acceptance for This Step

- All 9 docstrings show both Windows and Linux/macOS paths.
- Repo-wide grep for `~/.mcp_coder/config.toml` returns only lines that
  also contain `on Windows` (i.e. part of a dual-path sentence).
- Pylint, pytest, mypy all green.
- One commit produced.
