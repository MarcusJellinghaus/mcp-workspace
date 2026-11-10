"""Subprocess import checks for the exported toolset.

Each test runs in a fresh interpreter, so ``sys.modules`` shows exactly what
importing ``mcp_workspace.toolset`` and building the tools pulled in:

* the toolset must work without the ``mcp`` SDK, and
* building the tools must leave GitPython, PyGithub and markdown-it-py lazy.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Exercise the code under test from ``src`` (matching pytest's
# pythonpath=["src"]), never an installed copy in site-packages.
SRC_DIR = str(Path(__file__).resolve().parents[2] / "src")

_SETUP = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "import mcp_workspace.toolset\n"
    "from mcp_workspace.toolset import tool_specs\n"
)


def _run(code: str, *args: str) -> dict[str, Any]:
    """Run code in a fresh interpreter with src on PYTHONPATH; return the JSON it prints last."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SRC_DIR + (os.pathsep + existing if existing else "")
    proc = subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    data: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
    # Ensure we tested the src tree, not an installed package.
    assert SRC_DIR in data["file"], f"tested wrong copy: {data['file']}"
    return data


def test_toolset_does_not_import_mcp(tmp_path: Path) -> None:
    """Building the tools and calling a read and a write tool never loads ``mcp``."""
    code = _SETUP + (
        "fns = {s.name: s.fn for s in tool_specs(Path(sys.argv[1]))}\n"
        "fns['save_file']('a.txt', 'x')\n"
        "fns['read_file']('a.txt')\n"
        "print(json.dumps({\n"
        "    'mcp': any(m == 'mcp' or m.startswith('mcp.') for m in sys.modules),\n"
        "    'file': mcp_workspace.toolset.__file__,\n"
        "}))\n"
    )
    data = _run(code, str(tmp_path))

    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "x"
    assert data["mcp"] is False, "mcp imported by the toolset"


def test_building_tools_keeps_git_and_github_lazy(tmp_path: Path) -> None:
    """``tool_specs`` must not import GitPython, PyGithub or markdown-it-py."""
    code = _SETUP + (
        "tool_specs(Path(sys.argv[1]))\n"
        "print(json.dumps({\n"
        "    'git': 'git' in sys.modules,\n"
        "    'github': 'github' in sys.modules,\n"
        "    'markdown_it': 'markdown_it' in sys.modules,\n"
        "    'file': mcp_workspace.toolset.__file__,\n"
        "}))\n"
    )
    data = _run(code, str(tmp_path))

    assert data["git"] is False, "GitPython imported by tool_specs"
    assert data["github"] is False, "PyGithub imported by tool_specs"
    assert data["markdown_it"] is False, "markdown-it-py imported by tool_specs"
