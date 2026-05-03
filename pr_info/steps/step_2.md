# Step 2 — Runtime Strings Use the `mcp_coder_utils` Helper

## LLM Prompt

> Read `pr_info/steps/summary.md` and the implementation done in
> `pr_info/steps/step_1.md`, then implement **Step 2** as defined in
> `pr_info/steps/step_2.md`. Update the three runtime user-facing strings
> so they reference the resolved config path via
> `get_user_config_path()` imported from `mcp_coder_utils`.
> Add the import at the top of each file. After implementation, run
> `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with the recommended `-n auto` and
> integration markers excluded), and `mcp__mcp-tools-py__run_mypy_check`.
> Run `mcp__mcp-tools-py__run_format_code`, then make exactly one commit
> for this step.

## WHERE

| File | Site (approx. line) | Type |
|------|---------------------|------|
| `src/mcp_workspace/github_operations/base_manager.py` | top-of-file imports | Add `from mcp_coder_utils.user_config import get_user_config_path`. |
| `src/mcp_workspace/github_operations/base_manager.py` | 201 | `ValueError` message in `BaseGitHubManager.__init__`. |
| `src/mcp_workspace/github_operations/base_manager.py` | 290 | `logger.error` in `_get_repository` (404 branch). |
| `src/mcp_workspace/github_operations/verification.py` | top-of-file imports | Add `from mcp_coder_utils.user_config import get_user_config_path`. |
| `src/mcp_workspace/github_operations/verification.py` | 129 | `install_hint` text in the `token_configured` `CheckResult`. |

## WHAT

### `base_manager.py`

```python
# imports (new line; do NOT extend the existing mcp_workspace.config import)
from mcp_coder_utils.user_config import get_user_config_path
```

```python
# line ~201 (ValueError)
raise ValueError(
    f"GitHub token not found. Configure it in {get_user_config_path()} "
    "or set GITHUB_TOKEN environment variable"
)
```

```python
# line ~290 (logger.error, 404 branch)
logger.error(
    "Repository not found: %s - Check that the repo exists, "
    "you have access, and the URL in %s is correct.",
    repo_url,
    get_user_config_path(),
)
```

### `verification.py`

```python
# imports
from mcp_coder_utils.user_config import get_user_config_path
```

```python
# line ~129 (install_hint)
install_hint=(
    f"Set GITHUB_TOKEN environment variable or add [github] token "
    f"to {get_user_config_path()}"
),
```

## HOW (Integration Points)

- Both files import `get_user_config_path` directly from
  `mcp_coder_utils.user_config`. Do **not** route the import through
  `mcp_workspace.config` — the helper is an upstream public utility, no
  re-export is needed.
- `get_user_config_path()` returns a `pathlib.Path`. In `f-string`
  interpolation Python calls `str()` automatically, so plain
  `{get_user_config_path()}` is equivalent to
  `str(get_user_config_path())`. For `logger.error` `%s`, `Path` formats
  correctly via `%s` as well.
- No signatures change. No new public API.

## ALGORITHM

Each site is a one-line string substitution. Pseudocode for the pattern
applied at every site:

```
old: "...~/.mcp_coder/config.toml..."
new: f"...{get_user_config_path()}..."   (or %s + get_user_config_path() arg for logger calls)
```

## DATA

No data structures change. The only observable difference is the rendered
text in `ValueError`, log output, and `CheckResult.install_hint`.

## Tests

No new tests are required:

- `get_user_config_path` is tested upstream in `mcp-coder-utils`.
- The runtime sites are pure string substitutions with no behavioral logic.
- Existing tests in `tests/github_operations/` exercise these code paths
  (`__init__`, 404 logging, verification `install_hint`) and will continue
  to pass — pylint and mypy will catch any typo in the import or call.

If any existing test asserts the *exact* old string, update its expected
text to match the new platform-aware form. (Inspect test failures from the
test run; do not pre-emptively rewrite.)

## Acceptance for This Step

- All three runtime sites use `get_user_config_path()`.
- `from mcp_coder_utils.user_config import get_user_config_path` is present
  at the top of `base_manager.py` and `verification.py`.
- The literal `~/.mcp_coder/config.toml` no longer appears in the **runtime
  code paths** of `base_manager.py` or `verification.py`. (The dual-path
  docstrings updated by Step 3 may still include the literal — this step's
  grep gate is intentionally limited to non-docstring lines, e.g.
  `grep -n "~/.mcp_coder/config.toml" base_manager.py | grep -v '"""'`.
  The comprehensive repo-wide grep gate runs in Step 3.)
- Pylint, pytest, mypy all green.
- One commit produced.
