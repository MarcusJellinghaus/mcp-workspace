# Step 3 — Dual-Path Docstring Updates

## LLM Prompt

> Read `pr_info/steps/summary.md` and the work done in `pr_info/steps/step_1.md`
> and `pr_info/steps/step_2.md`, then implement **Step 3** as defined in
> `pr_info/steps/step_3.md`. Replace the single-path docstring text in 9
> files with the dual-path form. This is a mechanical text replacement —
> no logic changes. After implementation, run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (with the recommended `-n auto` and integration markers excluded), and
> `mcp__tools-py__run_mypy_check`. Run `./tools/format_all.sh`, then make
> exactly one commit for this step.

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

- Use `mcp__workspace__edit_file` per file. Each find string is unique within
  its file, so a normal (non-`replace_all`) edit suffices.
- Do not modify the surrounding TOML example block.
- After all 9 edits, grep the project for the literal
  `(~/.mcp_coder/config.toml)` to confirm only the dual-path forms remain
  (no single-path occurrences).

## ALGORITHM

```
for each of the 9 files:
    open file
    locate the single-path sentence
    replace with the dual-path sentence
    save
```

## DATA

No data structures touched. No tests added or modified.

## Tests

None required — docstrings are documentation only and have no runtime
effect. The standard pylint / pytest / mypy verification confirms nothing
broke.

## Acceptance for This Step

- All 9 docstrings show both Windows and Linux/macOS paths.
- No remaining single-path `(~/.mcp_coder/config.toml)` strings outside of
  the dual-path sentences (grep confirms).
- Pylint, pytest, mypy all green.
- One commit produced.
