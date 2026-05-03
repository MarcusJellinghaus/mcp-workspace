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

> **Before starting:** ensure the upstream `mcp-coder-utils` release that
> exposes `mcp_coder_utils.user_config.get_user_config_path` is installed in
> your venv (e.g. `pip install -e ../mcp-coder-utils` or the published
> release). Otherwise `pytest` collection will fail with
> `ModuleNotFoundError: No module named 'mcp_coder_utils.user_config'`,
> which is **not** the "RED" TDD state — the tests should fail on the
> assertion, not on import.
>
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
| `pyproject.toml` | Introduce a `>=X.Y.Z` lower bound on `mcp-coder-utils` (currently unpinned) targeting the release that exposes `get_user_config_path`. **Pin scheme:** match the prevailing convention used by sibling deps in `pyproject.toml` — at the time of writing this is loose `>=X.Y.Z` with no upper cap (e.g. `mcp>=1.3.0`, `GitPython>=3.1.0`). Verify by reading the file before editing and apply the same scheme. If the existing `[tool.mcp-coder.install-from-github]` block has a `mcp-coder-utils @ git+https://...` entry, also update it to pin the same release tag (`@vX.Y.Z` ref) so the GitHub-install path matches the PyPI/version constraint. |

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

Apply this pattern uniformly across **all four** existing test classes
in `tests/test_config.py`:

| Class | Tests using `patch.object(Path, "home", ...)` |
|-------|------------------------------------------------|
| `TestReadConfigValue` | 5 |
| `TestGetGithubToken` | 3 (the env-var-only test does not patch `Path.home`) |
| `TestGetGithubTokenWithSource` | 3 (same caveat) |
| `TestGetTestRepoUrl` | 2 (same caveat) |

That is **~13 `patch.object(Path, "home", ...)` call sites across 16
total tests in 4 classes** (verify by reading `tests/test_config.py`
before editing — counts as of plan authoring; the implementer should
re-check). Every site that patches `Path.home` should be migrated to
patch `mcp_workspace.config.get_user_config_path` (or the equivalent
`tmp_path` fixture). Drop any `patch.object(Path, "home", ...)` and any
`patch.object(sys, "platform", ...)`. Remove the `import sys` from the
test module if no longer used.

No new test class is required — there is no local helper to test, and
`get_user_config_path` is the upstream library's responsibility to test.

## Acceptance for This Step

- `_read_config_value()` calls `get_user_config_path()` (no inline path
  literal).
- The docstring on `_read_config_value` is platform-neutral.
- `tests/test_config.py` no longer mocks `sys.platform` and passes on every
  platform (mocked helper or `tmp_path`-based fixture).
- `pyproject.toml` declares a lower-bound `mcp-coder-utils>=X.Y.Z` (matching
  the sibling-dep pin scheme) targeting the release that exposes
  `get_user_config_path`. If `[tool.mcp-coder.install-from-github]` lists
  `mcp-coder-utils`, that entry references the same release tag.
- Pylint, pytest, mypy all green.
- One commit produced.
