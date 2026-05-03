#!/usr/bin/env bash
# Two-env aware launcher for Claude Code (developer edition)
# Same two-env discovery as claude.sh, plus editable-install verification
# Assumes mcp-workspace is editable-installed (pip install -e .)

set -u
clear

PROJECT_VENV="$PWD/.venv"

# === Step 0: Project .venv must exist ===
if [ ! -f "$PROJECT_VENV/bin/activate" ]; then
    echo "ERROR: Local virtual environment not found at .venv"
    echo "Please run: tools/reinstall_local.sh"
    exit 1
fi

# === Step 1: Project env activation ===
# Activate .venv first so its mcp-coder install is discoverable on PATH.
echo "Activating project environment: $PROJECT_VENV"
# shellcheck disable=SC1091
source "$PROJECT_VENV/bin/activate"
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "ERROR: Failed to activate project virtual environment."
    echo "Please check $PROJECT_VENV/bin/activate"
    exit 1
fi

# === Step 2: Tool env discovery ===
# Determine where mcp-coder is installed (tool env bin dir).
# For local dev, the project .venv (just activated) IS the tool env.
TOOL_VENV_BIN=""

MCP_CODER_PATH="$(command -v mcp-coder 2>/dev/null || true)"
if [ -n "$MCP_CODER_PATH" ]; then
    TOOL_VENV_BIN="$(cd "$(dirname "$MCP_CODER_PATH")" && pwd)"
fi

if [ -z "$TOOL_VENV_BIN" ]; then
    echo "ERROR: Cannot find mcp-coder installation."
    echo
    echo "Either:"
    echo "  1. Activate the tool environment: source path/to/tool/.venv/bin/activate"
    echo "  2. Ensure mcp-coder is on your PATH: pip install mcp-coder"
    echo "  3. Run: tools/reinstall_local.sh"
    exit 1
fi

# === Step 3: Set tool env variables ===
MCP_CODER_VENV_PATH="$TOOL_VENV_BIN"
MCP_CODER_VENV_DIR="$(cd "$MCP_CODER_VENV_PATH/.." && pwd)"

# === Step 4: Editable install verification ===
if ! "$PROJECT_VENV/bin/python" -c "from importlib.metadata import distribution as D; u=D('mcp-workspace').read_text('direct_url.json') or ''; exit(0 if 'dir_info' in u and 'editable' in u else 1)" 2>/dev/null; then
    echo "WARNING: mcp-workspace does not appear to be editable-installed from $PWD"
    echo "  For development, run: pip install -e ."
    echo "  Continuing anyway..."
fi

# === Step 5: MCP tool verification ===
if [ ! -x "$MCP_CODER_VENV_PATH/mcp-tools-py" ]; then
    echo "ERROR: mcp-tools-py not found in $MCP_CODER_VENV_PATH"
    echo "Please run: tools/reinstall_local.sh"
    exit 1
fi
if [ ! -x "$MCP_CODER_VENV_PATH/mcp-workspace" ]; then
    echo "ERROR: mcp-workspace not found in $MCP_CODER_VENV_PATH"
    echo "Please run: tools/reinstall_local.sh"
    exit 1
fi

# === Step 5b: Print MCP server versions ===
"$MCP_CODER_VENV_PATH/mcp-workspace" --version
"$MCP_CODER_VENV_PATH/mcp-tools-py" --version

# === Step 6: Set env vars ===
export MCP_CODER_VENV_PATH
export MCP_CODER_VENV_DIR
export MCP_CODER_PROJECT_DIR="$PWD"
export DISABLE_AUTOUPDATER=1
export PATH="$MCP_CODER_VENV_PATH:$PATH"

# === Step 7: Platform-specific MCP config override ===
# .mcp.json is Windows-only (uses .exe, backslashes, ${USERPROFILE}, \Lib\).
# On macOS/Linux, prefer a platform-specific file if present and fall back to
# the default .mcp.json otherwise.
MCP_CONFIG_OVERRIDE=""
case "$(uname)" in
    Darwin)
        if [ -f "$PWD/.mcp.macos.json" ]; then
            MCP_CONFIG_OVERRIDE="$PWD/.mcp.macos.json"
        fi
        ;;
    Linux)
        if [ -f "$PWD/.mcp.linux.json" ]; then
            MCP_CONFIG_OVERRIDE="$PWD/.mcp.linux.json"
        fi
        ;;
esac

echo "Starting Claude Code (developer mode) with:"
echo "  Tool env:     $MCP_CODER_VENV_PATH"
echo "  Project env:  $VIRTUAL_ENV"
echo "  Project dir:  $MCP_CODER_PROJECT_DIR"
echo "  Venv dir:     $MCP_CODER_VENV_DIR"
if [ -n "$MCP_CONFIG_OVERRIDE" ]; then
    echo "  MCP config:   $MCP_CONFIG_OVERRIDE (platform override)"
else
    echo "  MCP config:   .mcp.json (default)"
fi

CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
if [ -n "$MCP_CONFIG_OVERRIDE" ]; then
    exec "$CLAUDE_BIN" --mcp-config "$MCP_CONFIG_OVERRIDE" --strict-mcp-config "$@"
else
    exec "$CLAUDE_BIN" "$@"
fi
