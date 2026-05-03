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

## Upstream Prerequisite (BLOCKING)

Per the project's "shared utilities first" rule
(see `.claude/CLAUDE.md` -> Shared Libraries), `mcp_workspace` MUST NOT
duplicate platform-detection logic locally. The canonical resolver lives
today in `mcp_coder.utils.user_config.get_config_file_path()` (see
`mcp-coder` reference project, `src/mcp_coder/utils/user_config.py:160`).
That function is `mcp_coder`-internal, so we cannot import it from
`mcp_workspace`.

**This PR depends on `mcp-coder-utils` first exposing the helper.** Investigation
of the `mcp-coder-utils` reference project shows:

- Existing modules at the package root: `log_utils`, `redaction`,
  `subprocess_runner`, `subprocess_streaming`, plus an `fs/` subpackage.
- **No `config/` module and no path-resolution helper exists yet.**
- `mcp_coder_utils/__init__.py` only exports `__version__`.

**Suggested upstream addition** (file an issue/PR at
https://github.com/MarcusJellinghaus/mcp-coder-utils first):

- New module: `src/mcp_coder_utils/user_config.py`
  (mirrors the existing source name in `mcp_coder` for easy migration).
- Public function:

  ```python
  def get_user_config_path() -> Path:
      """Resolve the mcp_coder user-config file path.

      - Windows: ~/.mcp_coder/config.toml
      - Linux/macOS/Containers: ~/.config/mcp_coder/config.toml
      """
  ```

- The function name `get_user_config_path` is preferred over the upstream
  `get_config_file_path` because it is more self-describing at downstream
  call sites (e.g. `from mcp_coder_utils.user_config import get_user_config_path`).
  Final name to be agreed in the upstream PR.
- After the upstream release, `mcp_coder` itself should also switch
  `get_config_file_path` to delegate to the shared helper (out of scope for
  this PR).

**This PR cannot merge until** the upstream helper is released and
`mcp-coder-utils` in this repo's `pyproject.toml` is bumped to the version
that includes it.

## Architectural / Design Changes

This is a small, localized change.

- **No new local helper.** `mcp_workspace.config` imports the path resolver
  from `mcp_coder_utils` and uses it directly.
- **`_read_config_value()`** delegates to the imported helper instead of
  building the path inline.
- Two production modules (`base_manager.py`, `verification.py`) gain an
  import of the same helper from `mcp_coder_utils` so their runtime
  user-facing messages show the *actual* resolved path. They import
  directly from `mcp_coder_utils` (not via `mcp_workspace.config`) — the
  helper is a public utility, no need to re-export it.
- Class and test-module docstrings switch from a single Windows path to a
  dual-path note (Windows + Linux/macOS), since docstrings cannot call
  functions at import time.
- The Windows-specific docstring on `_read_config_value` itself
  (`config.py:10`) is replaced with a platform-neutral one-liner.

### Constraints preserved (from issue)

- No `$XDG_CONFIG_HOME` support — we mirror `mcp_coder`'s exact behavior so
  both packages converge on the same file.
- Runtime messages always show the actual resolved path so the displayed
  path matches the actual lookup.
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
src/mcp_workspace/config.py                                  # import + use mcp_coder_utils helper; update docstring
src/mcp_workspace/github_operations/base_manager.py          # 1 docstring + 2 runtime strings + import
src/mcp_workspace/github_operations/verification.py          # 1 runtime string + import
src/mcp_workspace/github_operations/pr_manager.py            # 1 docstring
src/mcp_workspace/github_operations/ci_results_manager.py    # 1 docstring
src/mcp_workspace/github_operations/issues/branch_manager.py # 1 docstring
src/mcp_workspace/github_operations/issues/manager.py        # 1 docstring
```

### Tests

```
tests/test_config.py                                                   # rework cross-platform tests using the imported helper / tmp_path
tests/github_operations/test_github_integration_smoke.py               # 1 module docstring
tests/github_operations/test_github_utils.py                           # 1 module docstring
tests/github_operations/test_issue_branch_manager_integration.py       # 1 module docstring
tests/github_operations/test_issue_manager_integration.py              # 1 module docstring
```

### Packaging

```
pyproject.toml                                                          # bump minimum mcp-coder-utils version (after upstream release)
```

## Implementation Steps (one commit each)

| Step | Scope | Test Strategy |
|------|-------|---------------|
| 1 | `config.py`: import the path helper from `mcp_coder_utils` and route `_read_config_value()` through it. Update its docstring to the platform-neutral form. Rework `tests/test_config.py` so existing tests no longer mock `sys.platform`. | Mock the imported `mcp_coder_utils` helper (or use `tmp_path` directly) so tests pass on every OS. |
| 2 | Runtime strings (3 sites): `base_manager.py:201`, `base_manager.py:290`, `verification.py:129`. Use the imported helper directly (no local wrapper). | Covered by Step 1's helper tests. No new behavioral tests required. Existing tests in `tests/github_operations/` continue to exercise these paths. |
| 3 | Docstrings (9 sites): 5 class docstrings + 4 test-module docstrings. Mechanical text replacement with the dual-path form. Run final repo-wide grep gate. | None — docstrings are documentation only. |

## Verification (every step)

After each step:

1. `mcp__mcp-tools-py__run_pylint_check`
2. `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
3. `mcp__mcp-tools-py__run_mypy_check`
4. `mcp__mcp-tools-py__run_format_code` before commit
