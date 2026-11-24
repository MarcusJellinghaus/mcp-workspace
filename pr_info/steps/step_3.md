# Step 3 — `execute_verify`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`.
> Follow TDD: write `tests/cli/test_verify.py` first, then
> `src/mcp_workspace/cli/verify.py`. Keep the exit code inline (no helper
> module). `cli/verify.py` must not import `mcp_workspace.main`. Run all checks
> listed below and make exactly one commit.

## WHERE

- Create `src/mcp_workspace/cli/verify.py`.
- Create `tests/cli/test_verify.py`.

## WHAT

```python
# cli/verify.py
from collections.abc import Mapping, Sequence
from pathlib import Path
from mcp_coder_utils.verify_render import STATUS_SYMBOLS, Row, SectionBuilder
from mcp_workspace._ssl import ensure_truststore
from mcp_workspace.cli.verify_formatting import (
    format_file_access_section, format_git_section,
    format_github_section, format_github_security_section,
)
from mcp_workspace.file_tools import verify_file_access
from mcp_workspace.git_operations import verify_git
from mcp_workspace.github_operations import github_security_rows, verify_github
from mcp_workspace.reference_projects import ReferenceProject
from mcp_workspace.traffic_log import set_traffic_log_context

def execute_verify(
    project_dir: Path,
    reference_projects: Mapping[str, ReferenceProject],
    rejected: Sequence[tuple[str, str]],
) -> int: ...
```

(Check the exact export locations of `verify_file_access` and `verify_git`
before importing; use the package-level exports.)

## ALGORITHM

```
ensure_truststore(); set_traffic_log_context(command="mcp-workspace verify")
with SectionBuilder() as out:
    out.open("FILE ACCESS"); result = verify_file_access(project_dir); files_ok = result["overall_ok"]
    out.add(*format_file_access_section(result, STATUS_SYMBOLS, label="workspace"))
    for name, ref in reference_projects.items():
        if ref.path.exists(): r = verify_file_access(ref.path); files_ok &= r["overall_ok"]; out.add(*format_file_access_section(r, STATUS_SYMBOLS, label=name))
        else: out.add(Row(name, STATUS_SYMBOLS["warning"], "path not found"))
    for label, reason in rejected: out.add(Row(label, STATUS_SYMBOLS["failure"], f"rejected: {reason}")); files_ok = False
    git = verify_git(project_dir, actually_sign=True); out.section("GIT", format_git_section(git, STATUS_SYMBOLS))
    github = verify_github(project_dir); out.section("GITHUB", format_github_section(github, STATUS_SYMBOLS))
    out.section("GITHUB SECURITY", format_github_security_section(github_security_rows(project_dir), STATUS_SYMBOLS))
return 0 if files_ok and git.get("overall_ok") and github.get("overall_ok") else 1
```

`out.section(...)` closes the open FILE ACCESS section first (SectionBuilder
behaviour), so all FILE ACCESS rows share one label width.

## DATA

- `reference_projects`: accepted references, key = final (auto-renamed) name.
- `rejected`: `(label, reason)` tuples, already credential-scrubbed by the caller;
  reason is one of `old format`, `missing name`, `missing path`,
  `path not found`, `not a directory`, `same directory as workspace`,
  `inside workspace`, `parent of workspace`.
- Return: `0` or `1`. GITHUB SECURITY never affects it. A missing reference
  path (`[WARN] path not found`) never affects it.

## Tests — `tests/cli/test_verify.py` (write first)

Patch at `mcp_workspace.cli.verify.<name>`: `verify_git`, `verify_github`,
`github_security_rows` (or `mcp_workspace.github_operations.security_rows.verify_github_security`
for security-section tests), `ensure_truststore`, `set_traffic_log_context`.
Use real `verify_file_access` with `tmp_path` rules files, or patch it.
Capture stdout with `capsys`; assert exact lines.

- Section order: `FILE ACCESS`, `GIT`, `GITHUB`, `GITHUB SECURITY` headers in that order.
- `ensure_truststore` called once; `set_traffic_log_context` called with
  `command="mcp-workspace verify"`; `verify_git` called with `actually_sign=True`.
- FILE ACCESS rows: workspace first with label `workspace`; accepted references
  in dict order with their names; rejected rows last as
  `[ERR]  rejected: <reason>`; a long rejected label widens the section (all
  rows share one value column).
- Exit codes:
  - all ok → 0;
  - invalid workspace `.mcp-file-access` → 1;
  - invalid reference `.mcp-file-access` → 1;
  - any rejected entry → 1;
  - reference whose path does not exist → `[WARN] path not found`, exit 0;
  - ported from mcp_coder `test_verify_exit_codes_git.py` and
    `test_verify_exit_codes_github.py`: git `overall_ok` False → 1, GitHub
    `overall_ok` False → 1, both True → 0.
- GITHUB SECURITY (port `test_verify_github_security_section.py`):
  all rows rendered with their labels; exit 0 when every security row fails
  (exit-neutral); API rows pass through unmodified; no token (patch
  `verify_github_security` to return the five `ok=None, value="not checked",
  error="repository not accessible"` rows mcp-workspace produces) → each
  renders `[WARN] not accessible (repository not accessible)`.
- Token source (port `TestVerifyGithubTokenSource`): GITHUB section shows the
  `from GITHUB_TOKEN env var` / `from ~/.mcp_coder/config.toml` hint line.

## Checks (all must pass)

`run_format_code`, `run_ruff_check`, `run_pylint_check`, `run_mypy_check`,
`run_pytest_check(extra_args=["-n", "auto"])`, `run_lint_imports_check`,
`run_tach_check`, `run_vulture_check`.

## Commit

`feat(cli): add execute_verify`
