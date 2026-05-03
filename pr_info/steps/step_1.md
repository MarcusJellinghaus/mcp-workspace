# Step 1 — Platform-Aware `_config_path()` Helper

## LLM Prompt

> Read `pr_info/steps/summary.md` and then implement **Step 1** as defined in
> `pr_info/steps/step_1.md`. Use TDD: write the new tests in
> `tests/test_config.py` first, run them and confirm they fail, then add
> `_config_path()` and route `_read_config_value()` through it until the
> tests pass. After implementation, run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check` (with the recommended `-n auto` and
> integration markers excluded), and `mcp__tools-py__run_mypy_check`. Run
> `./tools/format_all.sh`, then make exactly one commit for this step.

## WHERE

| File | Action |
|------|--------|
| `src/mcp_workspace/config.py` | Add `import sys`. Add private helper `_config_path()`. Refactor `_read_config_value()` to call it. |
| `tests/test_config.py` | Add tests for `_config_path()`. Update existing `_read_config_value` / `get_github_token` / `get_test_repo_url` tests so they remain platform-independent. |

## WHAT

```python
# src/mcp_workspace/config.py

import sys
from pathlib import Path


def _config_path() -> Path:
    """Resolve the user-config path, mirroring mcp_coder's logic."""
    if sys.platform == "win32":
        return Path.home() / ".mcp_coder" / "config.toml"
    return Path.home() / ".config" / "mcp_coder" / "config.toml"


def _read_config_value(section: str, key: str) -> str | None:
    """Read a value from the user config file."""
    config_path = _config_path()
    if not config_path.exists():
        return None
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        return data.get(section, {}).get(key)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return None
```

## HOW (Integration Points)

- `_config_path` is **private** (single leading underscore). Internal callers
  in `github_operations/` will import it directly as
  `from mcp_workspace.config import _config_path` in Step 2. No public API
  is added.
- `_read_config_value` is the only consumer in this step.
- No changes to `get_github_token`, `get_github_token_with_source`, or
  `get_test_repo_url` — they keep delegating to `_read_config_value`.

## ALGORITHM

```
_config_path():
    if sys.platform == "win32":
        return ~/.mcp_coder/config.toml
    else:
        return ~/.config/mcp_coder/config.toml

_read_config_value(section, key):
    path = _config_path()
    if not path.exists(): return None
    try: parse TOML; return data[section][key] or None
    except: return None
```

## DATA

- `_config_path()` → `pathlib.Path`. Always returns a value (no `None`).
- `_read_config_value()` → `str | None`. Unchanged signature.

## Tests to Add (TDD — write first)

In `tests/test_config.py`:

```python
import sys
from unittest.mock import patch

from mcp_workspace.config import _config_path


class TestConfigPath:
    """Tests for _config_path() platform branching."""

    def test_returns_windows_path_on_win32(self, tmp_path: Path) -> None:
        with (
            patch.object(sys, "platform", "win32"),
            patch.object(Path, "home", return_value=tmp_path),
        ):
            assert _config_path() == tmp_path / ".mcp_coder" / "config.toml"

    def test_returns_xdg_path_on_linux(self, tmp_path: Path) -> None:
        with (
            patch.object(sys, "platform", "linux"),
            patch.object(Path, "home", return_value=tmp_path),
        ):
            assert _config_path() == (
                tmp_path / ".config" / "mcp_coder" / "config.toml"
            )

    def test_returns_xdg_path_on_darwin(self, tmp_path: Path) -> None:
        with (
            patch.object(sys, "platform", "darwin"),
            patch.object(Path, "home", return_value=tmp_path),
        ):
            assert _config_path() == (
                tmp_path / ".config" / "mcp_coder" / "config.toml"
            )
```

## Tests to Update (cross-platform safety)

The existing tests in `TestReadConfigValue`, `TestGetGithubToken`,
`TestGetGithubTokenWithSource`, and `TestGetTestRepoUrl` write to
`tmp_path / ".mcp_coder"`. After this step they would fail on Linux/macOS
because the resolved path would be `~/.config/mcp_coder/...`.

**Minimal fix:** wrap each existing test with `patch.object(sys, "platform", "win32")`
in addition to the existing `patch.object(Path, "home", ...)`. This pins the
tests to the Windows branch they already exercise, keeping their structure
intact. Add `import sys` to the test module if not already present.

Example pattern for each existing test:

```python
def test_returns_value_when_present(self, tmp_path: Path) -> None:
    config_dir = tmp_path / ".mcp_coder"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[github]\ntoken = "ghp_test123"\n', encoding="utf-8"
    )
    with (
        patch.object(sys, "platform", "win32"),
        patch.object(Path, "home", return_value=tmp_path),
    ):
        assert _read_config_value("github", "token") == "ghp_test123"
```

## Acceptance for This Step

- `_config_path()` exists and is platform-aware.
- `_read_config_value()` calls `_config_path()` (no inline path literal).
- New `TestConfigPath` class covers `win32`, `linux`, and `darwin`.
- Existing config tests still pass on every platform.
- Pylint, pytest, mypy all green.
- One commit produced.
