"""Integration performance tests for MCP server startup (issue #212).

The server is spawned as a fresh OS process on every launch, so import cost is
paid every time. PyGithub (``github``) and GitPython (``git``) together pull in
~200 extra module files; importing them eagerly dominated cold-start time.
These tests lock in the optimization:

* importing ``mcp_workspace.server`` must NOT eagerly import those heavy libs,
* the common ``file_tools`` path must NOT pull in GitPython, and
* a full, real-process import must stay comfortably under three seconds.

These are integration tests: each spawns a real Python interpreter so that
"did importing X pull in Y?" and "how long does a cold import take?" are
measured in a fresh process where nothing is cached -- exactly how the MCP
client launches the server.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Exercise the code under test from ``src`` (matching pytest's
# pythonpath=["src"]), never an installed copy in site-packages.
SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")


def _fresh_env() -> dict[str, str]:
    """Environment with ``src`` first on PYTHONPATH for a clean subprocess."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SRC_DIR + (os.pathsep + existing if existing else "")
    return env


def _run(code: str) -> str:
    """Run *code* in a fresh interpreter; return stdout or fail with stderr."""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=_fresh_env(),
        timeout=60,
    )
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    return proc.stdout.strip()


def _time_process(code: str) -> float:
    """Wall-clock seconds for a full process spawn that runs *code*."""
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=_fresh_env(),
        timeout=60,
    )
    elapsed = time.perf_counter() - start
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    return elapsed


def test_server_import_does_not_eagerly_load_github_or_gitpython() -> None:
    """Importing the server module must not drag in PyGithub or GitPython."""
    code = (
        "import sys, json, mcp_workspace.server as s; "
        "print(json.dumps({"
        "'github': 'github' in sys.modules, "
        "'git': 'git' in sys.modules, "
        "'file': s.__file__}))"
    )
    data = json.loads(_run(code).splitlines()[-1])

    # Ensure we tested the src tree, not an installed package.
    assert SRC_DIR in data["file"], f"tested wrong copy: {data['file']}"
    assert data["github"] is False, "PyGithub imported eagerly at server import"
    assert data["git"] is False, "GitPython imported eagerly at server import"


def test_file_tools_import_does_not_load_gitpython() -> None:
    """The common file-operations path must not pull in GitPython.

    ``file_tools`` is on the hot path for read/write/edit/list/search; only the
    rarely-used git-aware *move* needs GitPython, and it imports it lazily.
    """
    code = (
        "import sys, json, mcp_workspace.file_tools; "
        "print(json.dumps({'git': 'git' in sys.modules}))"
    )
    data = json.loads(_run(code).splitlines()[-1])
    assert data["git"] is False, "GitPython imported eagerly via file_tools"


def test_server_startup_under_two_seconds() -> None:
    """A full real-process import of the server must stay under two seconds.

    Median of three spawns (after a warm-up that compiles bytecode) keeps this
    robust against one-off scheduler noise on CI. Warm import runs ~1s, so 2s
    still leaves comfortable headroom.
    """
    code = "import mcp_workspace.server"

    _time_process(code)  # warm-up: compile .pyc so we measure import, not compile

    samples = sorted(_time_process(code) for _ in range(3))
    median = samples[1]
    assert median < 2.0, (
        f"server startup too slow: {median:.3f}s "
        f"(samples={[round(s, 3) for s in samples]})"
    )
