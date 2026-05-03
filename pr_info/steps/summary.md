# Summary — Platform-Aware Config Path (Issue #184)

## Problem

`mcp_workspace.config._read_config_value()` hardcodes the user-config path
to `~/.mcp_coder/config.toml`, which is the **Windows-only** location.
On Linux/macOS, `mcp_coder` writes its config to `~/.config/mcp_coder/config.toml`,
so `mcp_workspace` reads an empty path and reports

```
GitHub token not found.
```

even when the token is configured correctly for `mcp_coder`.

## Goal

Make `mcp_workspace` resolve the same config-file path as `mcp_coder` on every
platform, and align all user-facing strings (errors, log messages, docstrings)
that mention the path.

## Architectural / Design Changes

This is a small, localized change. No new modules, no public-API additions,
no dependency changes.

- **One new private helper** in the existing leaf `config.py` module:
  `_config_path() -> Path`. It branches on `sys.platform`:
  - `win32` → `~/.mcp_coder/config.toml`
  - other  → `~/.config/mcp_coder/config.toml`
- **`_read_config_value()`** delegates to `_config_path()` instead of building
  the path inline.
- Two production modules (`base_manager.py`, `verification.py`) gain a private
  cross-module import of `_config_path` so their runtime user-facing messages
  show the *actual* resolved path via `str(_config_path())`. This is permitted
  because `config` sits in the Utilities layer that everything depends on
  (per `docs/ARCHITECTURE.md`).
- Class and test-module docstrings switch from a single Windows path to a
  dual-path note (Windows + Linux/macOS), since docstrings cannot call
  functions at import time.
- `_config_path` stays **private** (underscore prefix). Cross-module private
  imports within the same package are intentional here — no public API
  surface added.

### Constraints preserved (from issue)

- No `$XDG_CONFIG_HOME` support — we mirror `mcp_coder`'s exact behavior so
  both packages converge on the same file.
- Runtime messages always use `str(_config_path())` so the displayed path
  matches the actual lookup.
- Docstrings use the dual-path explicit form.

## Files Created

```
pr_info/steps/summary.md             # this document
pr_info/steps/step_1.md
pr_info/steps/step_2.md
pr_info/steps/step_3.md
```

## Files Modified

### Source

```
src/mcp_workspace/config.py                                  # add _config_path(), use it in _read_config_value()
src/mcp_workspace/github_operations/base_manager.py          # 1 docstring + 2 runtime strings + import
src/mcp_workspace/github_operations/verification.py          # 1 runtime string + import
src/mcp_workspace/github_operations/pr_manager.py            # 1 docstring
src/mcp_workspace/github_operations/ci_results_manager.py    # 1 docstring
src/mcp_workspace/github_operations/issues/branch_manager.py # 1 docstring
src/mcp_workspace/github_operations/issues/manager.py        # 1 docstring
```

### Tests

```
tests/test_config.py                                                   # add _config_path() tests; harden existing tests for cross-platform
tests/github_operations/test_github_integration_smoke.py               # 1 module docstring
tests/github_operations/test_github_utils.py                           # 1 module docstring
tests/github_operations/test_issue_branch_manager_integration.py       # 1 module docstring
tests/github_operations/test_issue_manager_integration.py              # 1 module docstring
```

## Implementation Steps (one commit each)

| Step | Scope | Test Strategy |
|------|-------|---------------|
| 1 | `config.py`: add `_config_path()`; route `_read_config_value()` through it. Update tests in `tests/test_config.py`. | TDD — write `_config_path()` tests first; update existing `_read_config_value` tests to be platform-independent. |
| 2 | Runtime strings (3 sites): `base_manager.py:201`, `base_manager.py:290`, `verification.py:129`. Use `str(_config_path())`. | Covered indirectly by Step 1's `_config_path()` tests. No new behavioral tests needed — pylint + mypy + existing pytest verify the strings render. |
| 3 | Docstrings (9 sites): 5 class docstrings + 4 test-module docstrings. Mechanical text replacement with the dual-path form. | None — docstrings are documentation only. |

## Verification (every step)

After each step:

1. `mcp__tools-py__run_pylint_check`
2. `mcp__tools-py__run_pytest_check` with `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
3. `mcp__tools-py__run_mypy_check`
4. `./tools/format_all.sh` before commit
