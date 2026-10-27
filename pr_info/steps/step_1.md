# Step 1: Config switch `get_traffic_log_dir()` + autouse test fixture

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` only.
> TDD: write the tests first, then the implementation. Run pylint, pytest
> (`extra_args: ["-n", "auto"]`) and mypy until all pass. Format with `run_format_code`,
> then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/config.py` — new function
- `tests/conftest.py` — new autouse fixture
- `tests/test_config.py` — new test class

## WHAT

```python
@functools.cache
def get_traffic_log_dir() -> Path | None:
    """Resolve the GitHub traffic log directory from ``[github]`` once per process.

    Returns:
        The directory when ``traffic_log = true``, else None (log off).
    """
```

## HOW

- `import functools` and `from pathlib import Path` in `config.py`.
- Read the `[github]` section directly from `_load_config()` (one file read). Don't reuse
  `_read_config_value`: it is typed `-> str | None`, which fits neither the bool
  `traffic_log` nor an `isinstance` narrowing without casts. `_load_config`,
  `get_github_token*` and `get_trusted_commenters` stay uncached.
- Other code must call it as `config.get_traffic_log_dir()` (module attribute) so the fixture
  replacement takes effect. Note this in the docstring.
- Fixture in `tests/conftest.py`, next to `_empty_trusted_commenters`:

```python
@pytest.fixture(autouse=True)
def _traffic_log_off(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Keep tests from reading the real traffic-log config or writing log files."""
    original = config.get_traffic_log_dir
    original.cache_clear()
    monkeypatch.setattr("mcp_workspace.config.get_traffic_log_dir", lambda: None)
    yield
    original.cache_clear()
```

  `tests/test_config.py` imports `get_traffic_log_dir` directly at module level, so it tests
  the real function (same pattern as `get_trusted_commenters`).

## ALGORITHM

```
section = _load_config().get("github", {})
if not isinstance(section, dict) or section.get("traffic_log") is not True: return None
value = section.get("traffic_log_dir")
if isinstance(value, str) and value: return Path(value)
return get_user_app_data_dir("mcp_coder") / "logs" / "github_traffic"
```

## DATA

- `Path | None`. No warnings for bad values; non-bool `traffic_log` → off, non-string or empty
  `traffic_log_dir` → default.

## Tests (`tests/test_config.py`, class `TestGetTrafficLogDir`)

Patch `mcp_workspace.config.get_user_app_data_dir` to `tmp_path` as the existing tests do, and
call `get_traffic_log_dir.cache_clear()` at the start of each test.

- file missing → `None`
- `traffic_log = false` / key missing / `traffic_log = "true"` (string) → `None`
- `traffic_log = true`, no dir → `tmp_path / "logs" / "github_traffic"`
- `traffic_log = true`, `traffic_log_dir = "D:/logs/gh"` → `Path("D:/logs/gh")`
- `traffic_log_dir = 5` or `""` → default dir
- cached: after the first call, rewriting the file doesn't change the result
- `get_trusted_commenters` still re-reads the file after `get_traffic_log_dir` was cached
