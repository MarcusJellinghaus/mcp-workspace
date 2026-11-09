# Step 13 — Subprocess import tests: no `mcp`, lazy git/GitHub

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_13.md`.
> Add two subprocess tests in `tests/toolset/test_toolset_imports.py`:
> (1) importing `mcp_workspace.toolset`, building the tools and calling a read and a write tool
> leaves `mcp` out of `sys.modules`; (2) `tool_specs(tmp_path)` leaves `git`, `github` and
> `markdown_it` out of `sys.modules`. Run all checks, format, commit.

## WHERE

- `tests/toolset/test_toolset_imports.py` (new)
- `tests/test_startup_performance.py` stays as is (import-only checks). Update its module docstring
  to point to the new file for tool-building coverage.

## WHAT

```python
SRC_DIR = str(Path(__file__).resolve().parents[2] / "src")

def _run(code: str, *args: str) -> dict[str, Any]:
    """Run code in a fresh interpreter with src on PYTHONPATH; return the JSON it prints last."""

def test_toolset_does_not_import_mcp(tmp_path: Path) -> None: ...
def test_building_tools_keeps_git_and_github_lazy(tmp_path: Path) -> None: ...
```

## HOW

- Same subprocess pattern as `tests/test_startup_performance.py`: `sys.executable -c`, `src` first on
  `PYTHONPATH`, `timeout=60`, `check=False`, and assert `returncode == 0` with stderr in the message.
  Pass `tmp_path` as `sys.argv[1]`.
- Also print `mcp_workspace.toolset.__file__` and assert it is under `SRC_DIR`, so the test checks the
  `src` tree rather than an installed copy.
- `mcp` check: `any(m == "mcp" or m.startswith("mcp.") for m in sys.modules)`. Not a prefix check
  on `"mcp"` alone: `mcp_workspace` and `mcp_coder_utils` share that prefix.
- If test (1) fails because a *dependency* (not `mcp_workspace`) imports `mcp`, write one line
  to `pr_info/.blocked.txt` naming the importing module, and stop.

## ALGORITHM

Code run in the subprocess for test (1):

```
import json, sys; from pathlib import Path
from mcp_workspace.toolset import tool_specs
fns = {s.name: s.fn for s in tool_specs(Path(sys.argv[1]))}
fns["save_file"]("a.txt", "x"); fns["read_file"]("a.txt")
print(json.dumps({"mcp": any(m == "mcp" or m.startswith("mcp.") for m in sys.modules), "file": ...}))
```

Test (2): same setup, but only `tool_specs(...)`, then print `"git"`, `"github"` and `"markdown_it"` membership.

## DATA

Each subprocess prints a single JSON line: `{"mcp": false, ...}` / `{"git": false, "github": false, "markdown_it": false, ...}`.

## Checks

All checks pass. One commit: `test(toolset): subprocess checks for mcp-free and lazy imports`.
