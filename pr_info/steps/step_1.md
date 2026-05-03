# Step 1 — Use `mcp_coder_utils` Path Helper in `config.py`

## Upstream Prerequisite

This step depends on `mcp_coder_utils` exposing a public path-resolver
(see `summary.md` -> "Upstream Prerequisite"). Suggested public API:

```python
from mcp_coder_utils.user_config import get_user_config_path
```

If the upstream PR lands the helper under a different module/name (e.g.
`mcp_coder_utils.config.get_user_config_path` or
`mcp_coder_utils.paths.user_config_path`), update the import in this step
accordingly. **Do not start this step until the upstream release is
available.**

## LLM Prompt

> Read `pr_info/steps/summary.md` and then implement **Step 1** as defined in
> `pr_info/steps/step_1.md`. Use TDD: rewrite the affected tests in
> `tests/test_config.py` first (mocking the imported `mcp_coder_utils`
> helper or using `tmp_path` directly), run them and confirm they fail,
> then change `_read_config_value()` to delegate to the imported helper
> until the tests pass. Also update the module-level docstring on
> `_read_config_value` to be platform-neutral. After implementation, run
> `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with the recommended `-n auto` and
> integration markers excluded), and `mcp__mcp-tools-py__run_mypy_check`.
> Run `mcp__mcp-tools-py__run_format_code`, then make exactly one commit
> for this step.

## WHERE

| File | Action |
|------|--------|
| `src/mcp_workspace/config.py` | Add `from mcp_coder_utils.user_config import get_user_config_path`. Replace the inline path literal in `_read_config_value()` with a call to `get_user_config_path()`. Update its docstring (line 10) from "Read a value from `~/.mcp_coder/config.toml`." to "Read a value from the user config file." |
| `tests/test_config.py` | Drop `sys.platform` mocking. Mock `mcp_workspace.config.get_user_config_path` (or use a fixture that points it at `tmp_path`) so tests are platform-independent. |
| `pyproject.toml` | Bump the minimum `mcp-coder-utils` version constraint to the release that includes the helper. |

## WHAT

```python
# src/mcp_workspace/config.py

from pathlib import Path  # already present

import tomllib  # already present

from mcp_coder_utils.user_config import get_user_config_path


def _read_config_value(section: str, key: str) -> str | None:
    """Read a value from the user config file."""
    config_path = get_user_config_path()
    if not config_path.exists():
        return None
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        return data.get(section, {}).get(key)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return None
```

Note: `import sys` is **not** added — there is no local platform branching.
If a previous draft of this plan called for it, ignore that.

## HOW (Integration Points)

- `get_user_config_path` is the public, platform-aware resolver from
  `mcp_coder_utils`. Importing it from `mcp_coder_utils.user_config` keeps
  the dependency boundary explicit.
- No public API is added in `mcp_workspace`. `_read_config_value` keeps its
  signature.
- `get_github_token`, `get_github_token_with_source`, and
  `get_test_repo_url` are unchanged — they delegate to `_read_config_value`.

## ALGORITHM

```
_read_config_value(section, key):
    path = get_user_config_path()       # from mcp_coder_utils
    if not path.exists(): return None
    try: parse TOML; return data[section][key] or None
    except: return None
```

## DATA

- `_read_config_value()` -> `str | None`. Unchanged signature.
- No new local symbols.

## Tests to Rework (write first, TDD)

In `tests/test_config.py` the existing tests (`TestReadConfigValue`,
`TestGetGithubToken`, `TestGetGithubTokenWithSource`, `TestGetTestRepoUrl`)
currently rely on `patch.object(Path, "home", return_value=tmp_path)` plus
the assumption that the resulting path is `tmp_path / ".mcp_coder/config.toml"`.
With the helper imported from `mcp_coder_utils`, that assumption no longer
holds on Linux/macOS.

**Recommended pattern** — mock the imported helper so the test owns the
returned path directly:

```python
from unittest.mock import patch

def test_returns_value_when_present(self, tmp_path: Path) -> None:
    config_dir = tmp_path / ".mcp_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text(
        '[github]\ntoken = "ghp_test123"\n', encoding="utf-8"
    )
    with patch(
        "mcp_workspace.config.get_user_config_path",
        return_value=config_file,
    ):
        assert _read_config_value("github", "token") == "ghp_test123"
```

Apply this pattern uniformly across the existing test classes. Drop any
`patch.object(Path, "home", ...)` and any `patch.object(sys, "platform", ...)`.
Remove the `import sys` from the test module if no longer used.

No new test class is required — there is no local helper to test, and
`get_user_config_path` is the upstream library's responsibility to test.

## Acceptance for This Step

- `_read_config_value()` calls `get_user_config_path()` (no inline path
  literal).
- The docstring on `_read_config_value` is platform-neutral.
- `tests/test_config.py` no longer mocks `sys.platform` and passes on every
  platform (mocked helper or `tmp_path`-based fixture).
- `pyproject.toml` requires the `mcp-coder-utils` release that exposes the
  helper.
- Pylint, pytest, mypy all green.
- One commit produced.
