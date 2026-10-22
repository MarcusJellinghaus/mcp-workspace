# Step 1 — Config allowlist, trust helpers, README

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> Write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until they all
> pass, then make exactly one commit. Do not touch files outside this step.

## WHERE

- `src/mcp_workspace/config.py` (modify)
- `src/mcp_workspace/github_operations/trust.py` (new)
- `src/mcp_workspace/github_operations/__init__.py` (modify — re-export)
- `tests/conftest.py` (modify — autouse fixture)
- `tests/test_config.py` (modify — new test classes)
- `tests/github_operations/test_trust.py` (new)
- `README.md` (modify — new section after "Running the Server")

## WHAT

```python
# config.py
logger = logging.getLogger(__name__)

def _read_config_list(section: str, key: str) -> list[str]: ...
def get_trusted_commenters() -> frozenset[str]: ...

# github_operations/trust.py
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

def normalize_author_association(value: object) -> Optional[str]: ...
def is_trusted_author(
    login: Optional[str], association: Optional[str], trusted: frozenset[str]
) -> bool: ...
```

## HOW

- `trust.py` imports only `typing`. No PyGithub, so it stays cheap to import.
- `github_operations/__init__.py`: `from mcp_workspace.config import get_trusted_commenters`
  and `from .trust import is_trusted_author`. Add both to `__all__`. The layering
  (`github_operations` → `config`) is already allowed by `.importlinter`.
- `tests/conftest.py`: add an autouse fixture that patches
  `mcp_workspace.config.get_trusted_commenters` to return `frozenset()`. Tests then never read the real
  `~/.mcp_coder/config.toml`. `tests/test_config.py` imports the function at module level
  (bound before the patch), so it still tests the real function.
  ```python
  @pytest.fixture(autouse=True)
  def _empty_trusted_commenters(monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setattr("mcp_workspace.config.get_trusted_commenters", frozenset)
  ```
  The internal callers added in steps 3/4 must look the function up at call time through
  `mcp_workspace.config` (e.g. `from mcp_workspace import config` + `config.get_trusted_commenters()`).

## ALGORITHM

```
_read_config_list(section, key):
    read config.toml like _read_config_value (missing file / parse error -> [])
    value = data.get(section, {}).get(key); None -> []          # no warning
    not a list, or any entry not str -> logger.warning(...); return []   # fail closed
    return [v for v in value if v]                             # drop ""

get_trusted_commenters(): return frozenset(v.lower() for v in _read_config_list("github", "trusted_commenters"))

is_trusted_author(login, association, trusted):
    if association in TRUSTED_ASSOCIATIONS: return True
    return bool(login) and login.lower() in trusted
```

`normalize_author_association(value)`: `value if isinstance(value, str) else None`.

## DATA

- `_read_config_list` → `list[str]`. An empty list means missing or invalid.
- `get_trusted_commenters` → lowercased `frozenset[str]`. It reads the file on every call and
  ignores environment variables.
- `is_trusted_author` → `bool`.

## Tests (write first)

`tests/github_operations/test_trust.py`:
- each of `OWNER`, `MEMBER`, `COLLABORATOR` → trusted
- each of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, `FIRST_TIMER`, `NONE`, `MANNEQUIN`, `None` →
  untrusted (login not on the allowlist)
- allowlisted login matches case-insensitively, e.g. `"Dependabot[bot]"` vs `{"dependabot[bot]"}`.
  The `[bot]` suffix is required: `"dependabot"` does not match `{"dependabot[bot]"}`.
- `login=""` or `None` with `""` in `trusted` → untrusted
- `normalize_author_association("OWNER") == "OWNER"`; `MagicMock()`, `None`, `1` → `None`
- `is_trusted_author` and `get_trusted_commenters` are importable from `mcp_workspace.github_operations`

`tests/test_config.py` (patch `mcp_workspace.config.get_user_app_data_dir` to `tmp_path`, as the
existing tests do):
- missing file → `frozenset()`; missing key → `frozenset()`, with no warning logged (`caplog`)
- `trusted_commenters = ["Alice", "dependabot[bot]", ""]` → `{"alice", "dependabot[bot]"}`
- `trusted_commenters = "alice"` → empty, and a warning is logged
- `trusted_commenters = ["alice", 1]` → empty, and a warning is logged
- env var `TRUSTED_COMMENTERS` / `GITHUB_TRUSTED_COMMENTERS` set via `monkeypatch.setenv` →
  no effect

## README

Add a new section `## GitHub configuration` after "Running the Server":
- file location `~/.mcp_coder/config.toml` (the user app-data dir of `mcp_coder`)
- `[github]` keys: `token` (`GITHUB_TOKEN` env var takes precedence), `test_repo_url`
  (`GITHUB_TEST_REPO_URL` takes precedence), `trusted_commenters` (a list of logins, with no env override)
- the trust rule:
  - `OWNER` / `MEMBER` / `COLLABORATOR` or an allowlisted login (case-insensitive, `[bot]` suffix
    included) is trusted.
  - Everything else is withheld from `check_branch_status` and `github_pr_view` output and replaced by a count line.
  - Roles are relative to the repo being read, including with `reference_name`.
  - The allowlist lives outside the repo on purpose, so a PR cannot add itself.
- example:
  ```toml
  [github]
  token = "ghp_..."
  trusted_commenters = ["dependabot[bot]"]
  ```
