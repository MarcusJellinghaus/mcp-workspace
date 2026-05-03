# Step 2 — Runtime Strings Use `str(_config_path())`

## LLM Prompt

> Read `pr_info/steps/summary.md` and the implementation done in
> `pr_info/steps/step_1.md`, then implement **Step 2** as defined in
> `pr_info/steps/step_2.md`. Update the three runtime user-facing strings
> so they reference the resolved config path via `str(_config_path())`.
> Add the import to existing `from mcp_workspace.config import …` statements.
> After implementation, run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check` (with the recommended `-n auto` and
> integration markers excluded), and `mcp__tools-py__run_mypy_check`. Run
> `./tools/format_all.sh`, then make exactly one commit for this step.

## WHERE

| File | Site (approx. line) | Type |
|------|---------------------|------|
| `src/mcp_workspace/github_operations/base_manager.py` | 18 | Add `_config_path` to the existing `from mcp_workspace.config import get_github_token` line. |
| `src/mcp_workspace/github_operations/base_manager.py` | 201 | `ValueError` message in `BaseGitHubManager.__init__`. |
| `src/mcp_workspace/github_operations/base_manager.py` | 290 | `logger.error` in `_get_repository` (404 branch). |
| `src/mcp_workspace/github_operations/verification.py` | 14 | Add `_config_path` to the existing `from mcp_workspace.config import get_github_token_with_source` line. |
| `src/mcp_workspace/github_operations/verification.py` | 129 | `install_hint` text in the `token_configured` `CheckResult`. |

## WHAT

### `base_manager.py`

```python
# imports
from mcp_workspace.config import _config_path, get_github_token
```

```python
# line ~201 (ValueError)
raise ValueError(
    f"GitHub token not found. Configure it in {_config_path()} "
    "or set GITHUB_TOKEN environment variable"
)
```

```python
# line ~290 (logger.error, 404 branch)
logger.error(
    "Repository not found: %s - Check that the repo exists, "
    "you have access, and the URL in %s is correct.",
    repo_url,
    _config_path(),
)
```

### `verification.py`

```python
# imports
from mcp_workspace.config import _config_path, get_github_token_with_source
```

```python
# line ~129 (install_hint)
install_hint=(
    f"Set GITHUB_TOKEN environment variable or add [github] token "
    f"to {_config_path()}"
),
```

## HOW (Integration Points)

- Both files already import from `mcp_workspace.config`. Extend the existing
  import line — do not add a new line.
- `_config_path()` returns a `pathlib.Path`. In `f-string` interpolation
  Python calls `str()` automatically, so plain `{_config_path()}` is
  equivalent to `str(_config_path())` and is preferred for readability.
  For the `logger.error %s` call, `Path` formats correctly via `%s` as well.
- No signatures change. No new public API.

## ALGORITHM

Each site is a one-line string substitution. Pseudocode for the pattern
applied at every site:

```
old: "...~/.mcp_coder/config.toml..."
new: f"...{_config_path()}..."   (or %s + _config_path() arg for logger calls)
```

## DATA

No data structures change. The only observable difference is the rendered
text in `ValueError`, log output, and `CheckResult.install_hint`.

## Tests

No new tests are required:

- The platform branching of `_config_path()` is already covered by Step 1's
  `TestConfigPath`.
- The runtime sites are pure string substitutions with no behavioral logic.
- Existing tests in `tests/github_operations/` exercise these code paths
  (`__init__`, 404 logging, verification `install_hint`) and will continue
  to pass — pylint and mypy will catch any typo in the import or call.

If any existing test asserts the *exact* old string, update its expected
text to match the new platform-aware form. (Inspect test failures from the
test run; do not pre-emptively rewrite.)

## Acceptance for This Step

- All three runtime sites use `_config_path()`.
- No occurrences of the literal `~/.mcp_coder/config.toml` remain in
  `base_manager.py` or `verification.py` (use grep to confirm).
- Pylint, pytest, mypy all green.
- One commit produced.
