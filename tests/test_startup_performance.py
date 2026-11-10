"""Integration performance tests for MCP server startup (issue #212).

The server is spawned as a fresh OS process on every launch, so import cost is
paid every time. PyGithub (``github``) and GitPython (``git``) together pull in
~200 extra module files; importing them eagerly dominated cold-start time.
These tests lock in the optimization:

* importing ``mcp_workspace.server`` must NOT eagerly import those heavy libs,
* the common ``file_tools`` path must NOT pull in GitPython, and
* a full, real-process import must stay under three seconds.

These are integration tests: each spawns a real Python interpreter so that
"did importing X pull in Y?" and "how long does a cold import take?" are
measured in a fresh process where nothing is cached -- exactly how the MCP
client launches the server.

These checks cover imports only. Building and calling the exported tools is
covered by ``tests/toolset/test_toolset_imports.py``.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

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
        check=False,
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
        check=False,
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
        "'markdown_it': 'markdown_it' in sys.modules, "
        "'file': s.__file__}))"
    )
    data = json.loads(_run(code).splitlines()[-1])

    # Ensure we tested the src tree, not an installed package.
    assert SRC_DIR in data["file"], f"tested wrong copy: {data['file']}"
    assert data["github"] is False, "PyGithub imported eagerly at server import"
    assert data["git"] is False, "GitPython imported eagerly at server import"
    assert data["markdown_it"] is False, (
        "markdown-it-py imported eagerly at server import"
    )


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


@pytest.mark.performance
@pytest.mark.skipif(
    "PYTEST_XDIST_WORKER" in os.environ,
    reason="timing-sensitive: run alone with `pytest -n 0 -m performance`",
)
def test_server_startup_under_three_seconds() -> None:
    """A full real-process import of the server must stay under three seconds.

    Median of three spawns (after a warm-up that compiles bytecode) keeps this
    robust against one-off scheduler noise on CI.

    Expected timings on an idle dev machine: ``import mcp_workspace.server``
    ~1.5s, of which ``import mcp.server.fastmcp`` alone is ~1.3s; our own code
    adds only ~0.1-0.2s. Slower machines (fastmcp alone ~2.2s) and parallel
    runs push the median past 3s, so this test is skipped under xdist and run
    on its own instead: ``pytest -n 0 -m performance``. The measured times
    are printed; view them with ``-s`` or ``-rP``.
    """
    code = "import mcp_workspace.server"

    _time_process(code)  # warm-up: compile .pyc so we measure import, not compile

    samples = sorted(_time_process(code) for _ in range(3))
    median = samples[1]
    rounded = [round(s, 3) for s in samples]
    print(f"server startup: median={median:.3f}s samples={rounded}")
    assert median < 3.0, (
        f"server startup too slow: {median:.3f}s (samples={rounded}). "
        "Re-run it alone on an idle machine before treating it as a "
        "regression: pytest -n 0 -m performance"
    )
