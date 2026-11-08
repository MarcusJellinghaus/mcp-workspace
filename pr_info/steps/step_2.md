# Step 2 — `config.get_read_max_lines()` + conftest stub

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 2** exactly as described in `pr_info/steps/step_2.md`. Write the tests first, then the implementation. Run pylint, pytest (`-n auto`) and mypy via the MCP tools; all must pass. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/config.py`
- `tests/conftest.py`
- `tests/test_config.py`

## WHAT

```python
def get_read_max_lines() -> int | None:
    """Read ``[mcp_workspace] read_max_lines`` from the user config file.

    Returns:
        The configured value (``0`` = no limit) or None if not set or invalid.
    """
```

## HOW

- Build on the existing `_read_config_value("mcp_workspace", "read_max_lines")` (handles missing file / section / non-table section).
- No cache (`main.py` calls it once at startup).
- Warning message style follows `_read_config_list`: `"Ignoring [%s] %s in config.toml: expected a non-negative integer"`.
- `tests/conftest.py`: add autouse fixture next to `_empty_trusted_commenters`:

```python
@pytest.fixture(autouse=True)
def _no_read_max_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reading the real ``[mcp_workspace] read_max_lines``."""
    monkeypatch.setattr("mcp_workspace.config.get_read_max_lines", lambda: None)
```

  Note: `tests/test_config.py` imports `get_read_max_lines` directly at module import time, so its tests exercise the real function (same as the existing `get_trusted_commenters` tests).

## ALGORITHM

```
value = _read_config_value("mcp_workspace", "read_max_lines")
if value is None: return None
if isinstance(value, bool) or not isinstance(value, int) or value < 0:
    logger.warning(...); return None
return value
```

## DATA

`int | None` — `0` returned as-is.

## Tests (write first) — `tests/test_config.py`

Use the existing pattern (patch `mcp_workspace.config.get_user_app_data_dir` to `tmp_path`, write `config.toml`).

- No config file → `None`.
- `[mcp_workspace]` without the key → `None`.
- `read_max_lines = 500` → `500`.
- `read_max_lines = 0` → `0`.
- Parametrized invalid (`-1`, `true`, `"500"`, `1.5`) → `None` and a warning logged (`caplog`).
