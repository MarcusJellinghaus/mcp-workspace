# Step 9 — `verify_file_access` and startup warning (gap 11)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_9.md`.
> Write the tests first, then the code. Run pylint, pytest (`-n auto`), mypy, vulture,
> lint-imports and tach until all pass, run `run_format_code`, and make exactly one commit.

## Goal

`verify_file_access(project_dir)` reports the rules file as one `CheckResult` row plus
`overall_ok`, in the shape `verify_git` / `verify_github` use. It is exported at every public-API
site and called at startup for the workspace and each existing reference project.

## WHERE

- **New:** `src/mcp_workspace/file_tools/verification.py`, `tests/file_tools/test_verification.py`
- **Modified:**
  - `src/mcp_workspace/file_tools/file_access.py`, `file_tools/directory_utils.py`, `file_tools/__init__.py`
  - `src/mcp_workspace/main.py`, `vulture_whitelist.py`
  - `tests/file_tools/test_file_access.py`, `tests/test_main.py`
  - `docs/ARCHITECTURE.md`, `docs/file-access.md`, `docs/release-notes.md`

## WHAT

```python
"""Check a project's .mcp-file-access rules file."""

from __future__ import annotations   # CheckResult exists only for type checking

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from mcp_workspace.file_tools.access_rules import ACCESS_RULES_FILE, load_access_rules

if TYPE_CHECKING:
    from mcp_workspace.git_operations import CheckResult


class FileAccessVerification(TypedDict):
    """Result of verify_file_access."""

    rules_file: CheckResult
    overall_ok: bool


def verify_file_access(project_dir: Path) -> FileAccessVerification: ...
```

## ALGORITHM

```
rules = load_access_rules(project_dir)            # logs each problem once via _report
if rules.problems:
    row: CheckResult = {"ok": False, "value": "invalid", "severity": "error",
                        "error": "; ".join(rules.problems)}
elif not (project_dir / ACCESS_RULES_FILE).exists():
    row = {"ok": True, "value": "absent - gitignore only", "severity": "error"}
else:
    row = {"ok": True, "value": f"{len(rules.rules)} rules", "severity": "error"}
return {"rules_file": row, "overall_ok": row["ok"]}
```

Classify from problems first, because a directory at the path is reported as invalid with "is a
directory". Use `exists()`, not `is_file()`.

## DATA

| Case | `rules_file` | `overall_ok` |
|---|---|---|
| absent | `{"ok": True, "value": "absent - gitignore only", "severity": "error"}` | True |
| 2 rules | `{"ok": True, "value": "2 rules", "severity": "error"}` | True |
| comment-only | `{"ok": True, "value": "0 rules", "severity": "error"}` | True |
| invalid | `{"ok": False, "value": "invalid", "severity": "error", "error": "line 1: unknown level 'readonly'"}` | False |
| directory | `{"ok": False, "value": "invalid", "severity": "error", "error": "is a directory"}` | False |

## HOW

**Construction rules:**
- Rows are dict literals annotated as `CheckResult`. Never call `CheckResult(...)`: it is imported
  only under `TYPE_CHECKING`, so the call raises `NameError` at runtime.
- **Layering:** import only `access_rules` at runtime. `file_tools` must not import `git_operations`
  at runtime (GitPython), and must not import `github_operations` at all.

**Exports (all required, for mcp_coder's shim):**
- `file_access.py`: a runtime import (not under `TYPE_CHECKING`)
  `from mcp_workspace.file_tools.verification import FileAccessVerification as FileAccessVerification`
  and `… import verify_file_access as verify_file_access`.
- `directory_utils.py`: add both names to `_FILE_ACCESS_EXPORTS` and to its `TYPE_CHECKING` re-export block.
- `file_tools/__init__.py`: import both from `file_access` and add them to `__all__`.

**Startup (`main.py`):**
- Inside the existing lazy-import block (after `validate_reference_projects`, before `run_server`),
  import `verify_file_access` from `mcp_workspace.file_tools` alongside `DEFAULT_READ_MAX_LINES`.
- Then:
  ```
  verify_file_access(project_dir)
  for project in reference_projects.values():
      if project.path.exists():
          verify_file_access(project.path)
  ```
  The return value is ignored; the problems are logged by `_report`.

**Vulture:** run `run_vulture_check`. Whitelist in `vulture_whitelist.py` only the TypedDict
fields it flags (e.g. `_.rules_file`, `_.overall_ok`), next to the existing `_.ok` / `_.severity`
style entries.

## Precondition

If `run_lint_imports_check` or `run_tach_check` rejects the `TYPE_CHECKING` import of
`mcp_workspace.git_operations` from `file_tools`, write one line to `pr_info/.blocked.txt` and stop.

## Tests (write first)

- **`tests/file_tools/test_verification.py`:** one test parametrized over the five DATA rows, building
  `tmp_path` accordingly (no file / `read-only /a\nread-write /b\n` / `# comment\n` /
  `readonly /a\n` / a directory named `.mcp-file-access`). Assert the whole returned dict.
- **`tests/file_tools/test_file_access.py`:** extend `test_public_api_importable` and
  `test_public_api_reexported_from_directory_utils` to cover `verify_file_access` and
  `FileAccessVerification`, checking identity with the `file_access` objects.
- **`tests/test_main.py`:** a new test in `TestMain`, modelled on `test_main_with_reference_projects`.
  Patch `mcp_workspace.file_tools.verify_file_access` too, and assert it was called with the
  resolved project dir and both reference paths.
- The existing `tests/test_startup_performance.py::test_file_tools_import_does_not_load_gitpython`
  must stay green.

## Docs

- **`docs/ARCHITECTURE.md`, Access Layer:**
  - add `file_tools/verification.py   verify_file_access: rules-file check (startup)` to the
    module diagram;
  - add `verify_file_access` and `FileAccessVerification` to the sentence listing what
    `directory_utils` re-exports lazily.
- **`docs/file-access.md`, "Invalid rules file":** add the sentence "To check a rules file by hand,
  look for the startup log warning, or the first line of `list_directory` /
  `list_reference_directory`."
- **`docs/release-notes.md`, #404 section:** a bullet for the new public API
  `verify_file_access(project_dir) -> FileAccessVerification` (`rules_file`, `overall_ok`) in
  `mcp_workspace.file_tools`, `file_tools.file_access` and `file_tools.directory_utils`, and for
  the startup check.

## Commit

`feat(file_tools): add verify_file_access and check rules files at startup (#404)`
