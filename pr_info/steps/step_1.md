# Step 1 — `cli` package and section formatters

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
> Follow TDD: write `tests/cli/test_verify_formatting.py` first, then the
> implementation. Copy mcp_coder's `_format_section` logic verbatim (only
> renaming `_hint` → `hint_row`); do not redesign it. Run all checks listed
> below and make exactly one commit.

## Precondition

If `import mcp_coder_utils.verify_render` fails in the project environment
(mcp-coder-utils older than #84), write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- Create `src/mcp_workspace/cli/__init__.py` — module docstring only, no imports.
- Create `src/mcp_workspace/cli/verify_formatting.py`.
- Create `tests/cli/__init__.py` (empty) and `tests/cli/test_verify_formatting.py`.
- Modify `.importlinter`, `tach.toml`.

## WHAT

```python
# cli/verify_formatting.py
from collections.abc import Mapping
from typing import Any
from mcp_coder_utils.verify_render import Line, Row, hint_row

_LABEL_MAP: dict[str, str]                      # GitHub, GitHub security, Git entries only
_BRANCH_PROTECTION_CHILDREN: frozenset[str]

def _format_section(result: Mapping[str, Any], symbols: dict[str, str]) -> list[Line]: ...
def format_git_section(result: Mapping[str, Any], symbols: dict[str, str]) -> list[Line]: ...
def format_github_section(result: Mapping[str, Any], symbols: dict[str, str]) -> list[Line]: ...
def format_github_security_section(result: Mapping[str, Any], symbols: dict[str, str]) -> list[Line]: ...
def format_file_access_section(
    result: Mapping[str, Any], symbols: dict[str, str], *, label: str = ".mcp-file-access"
) -> list[Line]: ...
```

- `_LABEL_MAP`: copy the `# GitHub section`, `# GitHub security section` and
  `# Git section` entries from mcp_coder `verify_formatting._LABEL_MAP`
  (exact strings). Nothing else.
- `_format_section`: verbatim copy of mcp_coder `_format_section` (same loop,
  same branch-protection, `[Permissions]`, `token_source` hint text
  `from GITHUB_TOKEN env var` / `from ~/.mcp_coder/config.toml` plus
  ` (<fingerprint>)`, `-> <install_hint>` row). Only change: `_hint(...)` →
  `hint_row(...)`; parameter type `Mapping[str, Any]`. Keep the comment that it
  relies on `verify_github`'s dict key order.
- The three public `format_*_section` functions are one-line wrappers
  returning `_format_section(result, symbols)`; their docstrings say which
  producer they format (`verify_git`, `verify_github`, `github_security_rows`).
- Formatters return lines without a title; the caller opens the section.

## ALGORITHM — `format_file_access_section`

```
entry = result["rules_file"]; ok = entry.get("ok")
marker = symbols["success"] if ok is True else symbols["failure"] if ok is False else symbols["warning"]
value = str(entry.get("value", ""))
if ok is False and entry.get("error"): value = f"{value} ({entry['error']})"
return [Row(label, marker, value, wrap=ok is False)]   # only the invalid row wraps
```

## DATA

- Input `result`: a `verify_git` / `verify_github` / `github_security_rows`
  dict, or a `FileAccessVerification` (`{"rules_file": CheckResult, "overall_ok": bool}`).
- Output: `list[Line]` (`Row | str`), rendered by `render_rows` / `SectionBuilder`.

## HOW — config

- `.importlinter` layered contract: change the line `mcp_workspace.server` to
  `mcp_workspace.server | mcp_workspace.cli`; update the comment flow line to
  mention `cli`.
- `tach.toml`:
  - new module `mcp_workspace.cli`, `layer = "protocol"`, `depends_on` =
    `mcp_workspace.file_tools`, `mcp_workspace.git_operations`,
    `mcp_workspace.github_operations`, `mcp_workspace.reference_projects`,
    `mcp_workspace._ssl`, `mcp_workspace.traffic_log`, `mcp_workspace.utils`,
    `mcp_coder_utils.verify_render`;
  - new module `mcp_coder_utils.verify_render`, `layer = "utilities"`, `depends_on = []`;
  - `mcp_workspace.main` depends_on gains `mcp_workspace.cli` and `mcp_workspace.utils`;
  - `tests` depends_on gains `mcp_workspace.cli` and `mcp_coder_utils.verify_render`.

## Tests — `tests/cli/test_verify_formatting.py` (write first)

Port from mcp_coder `tests/cli/commands/` and assert exact text through
`render_rows(...)` with hardcoded columns (label width 22 → value column 32;
do not import mcp_coder conftest helpers or private `verify_render` names):

- `TestFormatSection` (from `test_verify_format_section_basic.py`) rewritten
  with git/GitHub keys (e.g. `git_binary`, `repo_url`): `ok=True` → `[OK]`,
  `ok=False` → `[ERR]` with `value (error)`, `ok=None` → `[WARN]`,
  `install_hint` rendered as `-> hint` row only when `ok is False`,
  `overall_ok` and non-dict entries skipped.
- `TestBranchProtectionNesting`, `TestGitHubLabelMappings`,
  `TestGitLabelMappings`, `TestAutoDeleteBranches`, `TestApiBaseUrlRendering`,
  `TestTokenFingerprintSuffix`, `TestPermissionProbes` — same file, using the
  public `format_github_section` / `format_git_section`.
- `test_github_permissions_section_aligned_with_token_hint` (from
  `test_verify_render.py`): value column 33 (label width 23), hint line is
  `" " * 33 + "from GITHUB_TOKEN env var"`.
- Token-source hint (from `test_verify.py::TestVerifyGithubTokenSource`):
  `token_source="env"` → `from GITHUB_TOKEN env var`; `"config"` →
  `from ~/.mcp_coder/config.toml`; with `token_fingerprint` → suffix ` (<fp>)`.
- `test_fixed_labels_fit_default_width`: every `_LABEL_MAP` value has length ≤ 22.
- `format_github_security_section`: security labels render (`Dependabot config`,
  `Secret push protection`, …).
- `format_file_access_section`: default label `.mcp-file-access`; custom label;
  `[OK] 3 rules`; `[OK] absent - gitignore only`; invalid →
  `[ERR]  invalid (line 4: …)`; a long problem string wraps at 80 columns with
  continuation lines starting at the value column.

If the file exceeds 750 lines, split it into `test_verify_formatting.py` and
`test_verify_formatting_github.py`.

## Checks (all must pass)

`run_format_code`, `run_ruff_check`, `run_pylint_check`, `run_mypy_check`,
`run_pytest_check(extra_args=["-n", "auto"])`, `run_lint_imports_check`,
`run_tach_check`, `run_vulture_check`.

## Commit

`feat(cli): add verify section formatters`
