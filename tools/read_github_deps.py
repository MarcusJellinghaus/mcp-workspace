"""Print uv pip install commands for GitHub dependency overrides.

Bootstrap helper for reinstall_local.bat. Reads [tool.mcp-coder.install-from-github]
from pyproject.toml without requiring any installed packages.

Default output (one command per line):
    uv pip install "pkg1" "pkg2"
    uv pip install --no-deps "pkg3"

With --specs, prints one spec from `packages` per line, no prefix and no
quoting, suitable for inlining into a single `uv pip install` invocation
(e.g. via bash `mapfile`). The `packages-no-deps` group is omitted in
this mode: those need their own `--no-deps` invocation.
"""

import sys
import tomllib
from pathlib import Path


def main(project_dir: Path | None = None) -> None:
    """Read GitHub install config and print uv pip install commands."""
    if project_dir is None:
        project_dir = Path(__file__).resolve().parent.parent
    path = project_dir / "pyproject.toml"

    if not path.exists():
        return

    with open(path, "rb") as f:
        data = tomllib.load(f)

    gh = data.get("tool", {}).get("mcp-coder", {}).get("install-from-github", {})

    packages = gh.get("packages", [])

    if "--specs" in sys.argv[1:]:
        for spec in packages:
            print(spec)
        return

    if packages:
        quoted = " ".join(f'"{p}"' for p in packages)
        print(f"uv pip install {quoted}")

    no_deps = gh.get("packages-no-deps", [])
    if no_deps:
        quoted = " ".join(f'"{p}"' for p in no_deps)
        print(f"uv pip install --no-deps {quoted}")


if __name__ == "__main__":
    main()
