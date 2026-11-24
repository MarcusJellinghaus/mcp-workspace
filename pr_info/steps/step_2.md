# Step 2 — `github_security_rows` and PyYAML

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`.
> Follow TDD: write `tests/github_operations/test_security_rows.py` first, then
> `src/mcp_workspace/github_operations/security_rows.py`. Move the helpers from
> mcp_coder `src/mcp_coder/cli/commands/verify_sections.py` with minimal
> changes; drop only the missing-key / `_NOT_ACCESSIBLE` fallback. Do not change
> `verify_github_security`. Run all checks listed below and make exactly one commit.

## Preconditions

- If `import yaml` fails in the project environment, write one line to
  `pr_info/.blocked.txt` and stop.
- If mypy reports missing library stubs for `yaml` (types-PyYAML not
  installed), write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- Create `src/mcp_workspace/github_operations/security_rows.py`.
- Modify `src/mcp_workspace/github_operations/__init__.py` (import + `__all__`).
- Modify `pyproject.toml`, `.importlinter`.
- Create `tests/github_operations/test_security_rows.py`.

## WHAT

```python
# github_operations/security_rows.py
import yaml
from mcp_workspace.github_operations._security_probes import verify_github_security
from mcp_workspace.github_operations._types import CheckResult

_CODEQL_ACTION_PREFIX = "github/codeql-action"

def _schedule_interval(entry: dict[str, Any]) -> Any: ...
def _workflow_uses_codeql(path: Path) -> bool: ...
def _check_dependabot_config(project_dir: Path) -> CheckResult: ...
def _check_codeql_workflow(project_dir: Path) -> CheckResult: ...
def _map_security_row(key: str, row: CheckResult) -> CheckResult: ...
def github_security_rows(project_dir: Path) -> dict[str, CheckResult]: ...
```

- The first four: copied unchanged from mcp_coder `verify_sections.py`.
- `_map_security_row`: mcp_coder's rules minus the `row is None` case:
  `entry = row.copy()`; `ok None` + `"not checked"` → `"not accessible"`;
  `code_scanning_alerts` with `ok False` and `"scope missing or not configured"`
  → `ok None`; `ok None` with `error` → `value = f"{value} ({error})"`.
  Keep the "Known false positive … 3xx redirect" comment.
- Import `verify_github_security` into the module namespace so tests can patch
  `mcp_workspace.github_operations.security_rows.verify_github_security`.

## ALGORITHM — `github_security_rows`

```
api = verify_github_security(project_dir)
return {
  "dependabot_config": _check_dependabot_config(project_dir),
  4 API keys in order (dependabot_alerts, dependabot_security_updates, secret_scanning,
     secret_scanning_push_protection): _map_security_row(key, api[key]),
  "codeql_workflow": _check_codeql_workflow(project_dir),
  "code_scanning_alerts": _map_security_row("code_scanning_alerts", api["code_scanning_alerts"]),
}
```

## DATA

`dict[str, CheckResult]` with exactly 7 keys in this order: `dependabot_config`,
`dependabot_alerts`, `dependabot_security_updates`, `secret_scanning`,
`secret_scanning_push_protection`, `codeql_workflow`, `code_scanning_alerts`.
All rows `severity="warning"`. No `overall_ok` key.

## HOW — config

- `pyproject.toml`: add `"PyYAML"` to `dependencies`; add `"types-PyYAML"` to
  the `dev` extra and to the `typecheck` extra.
- `github_operations/__init__.py`: `from .security_rows import github_security_rows`
  and add `"github_security_rows"` to `__all__`.
- `.importlinter`: new contract

  ```ini
  [importlinter:contract:yaml_isolation]
  name = PyYAML Library Isolation
  type = forbidden
  source_modules =
      mcp_workspace
  forbidden_modules =
      yaml
  ignore_imports =
      mcp_workspace.github_operations.security_rows -> yaml
  ```

  with a short comment block like the other isolation contracts. Update the
  header comment counts: "all nine contracts - including the six
  library-isolation ones" → "all ten contracts - including the seven
  library-isolation ones", and add `yaml` to the list of libraries in the
  following sentence.

## Tests — `tests/github_operations/test_security_rows.py` (write first)

Port from mcp_coder (adjust imports to `mcp_workspace.github_operations.security_rows`):

- `test_verify_sections_security.py`: dependabot config cases (missing,
  `.yml`/`.yaml`, invalid YAML, no ecosystems, one interval, mixed intervals),
  CodeQL workflow cases, and `TestMapSecurityRow` **without** the
  `code-scanning-missing-key` case. Do not port
  `test_section_missing_code_scanning_key_renders_warn`.
- `test_verify_github_security_probe.py`: patch only
  `mcp_workspace.github_operations._security_probes.BaseGitHubManager`; render
  via `render_rows(format_github_security_section(github_security_rows(tmp_path), STATUS_SYMBOLS))`.
  Cases: code scanning 200 → `[OK] scope present`; 403 → `[ERR]`; 404 →
  `[WARN] scope missing or not configured`; `ConnectionError("boom")` →
  `[WARN] not accessible (network error: boom)`; unresolvable repo → all five
  API rows `[WARN] not accessible (repository not accessible)`.
- `github_security_rows` key order equals the 7 keys above (patch
  `security_rows.verify_github_security`).

## Checks (all must pass)

`run_format_code`, `run_ruff_check`, `run_pylint_check`, `run_mypy_check`,
`run_pytest_check(extra_args=["-n", "auto"])`, `run_lint_imports_check`,
`run_tach_check`, `run_deptry_check`, `run_vulture_check`.

## Commit

`feat(github_operations): add github_security_rows`
