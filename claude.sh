#!/usr/bin/env bash
# Two-env aware launcher for Claude Code with MCP servers
# Discovers tool env (mcp-coder) separately from project env (.venv)
# Assumes you're running from the project root

set -u
clear

PROJECT_VENV="$PWD/.venv"

# === Step 1: Tool env discovery ===
# Determine where mcp-coder is installed (tool env bin dir)
TOOL_VENV_BIN=""

if [ -n "${VIRTUAL_ENV:-}" ] && [ "$VIRTUAL_ENV" != "$PROJECT_VENV" ]; then
    # VIRTUAL_ENV points to an external env — assume it's the tool env
    TOOL_VENV_BIN="$VIRTUAL_ENV/bin"
else
    # Fall back to PATH lookup
    MCP_CODER_PATH="$(command -v mcp-coder 2>/dev/null || true)"
    if [ -n "$MCP_CODER_PATH" ]; then
        TOOL_VENV_BIN="$(cd "$(dirname "$MCP_CODER_PATH")" && pwd)"
    fi
fi

if [ -z "$TOOL_VENV_BIN" ]; then
    echo "ERROR: Cannot find mcp-coder installation."
    echo
    echo "Either:"
    echo "  1. Activate the tool environment: source path/to/tool/.venv/bin/activate"
    echo "  2. Ensure mcp-coder is on your PATH: pip install mcp-coder"
    echo "  3. Install mcp-coder into .venv: pip install -e ."
    exit 1
fi

# === Step 2: Set tool env variables ===
MCP_CODER_VENV_PATH="$TOOL_VENV_BIN"
MCP_CODER_VENV_DIR="$(cd "$MCP_CODER_VENV_PATH/.." && pwd)"

# === Step 3: Project env activation ===
if [ -f "$PROJECT_VENV/bin/activate" ]; then
    echo "Activating project environment: $PROJECT_VENV"
    # shellcheck disable=SC1091
    source "$PROJECT_VENV/bin/activate"
    if [ -z "${VIRTUAL_ENV:-}" ]; then
        echo "ERROR: Failed to activate project virtual environment."
        echo "Please check $PROJECT_VENV/bin/activate"
        exit 1
    fi
else
    # Self-hosting fallback: no .venv, so tool env is also the project env
    echo "No project .venv found — using tool environment for both."
    export VIRTUAL_ENV="$MCP_CODER_VENV_DIR"
fi

# === Step 4: MCP tool verification ===
if [ ! -x "$MCP_CODER_VENV_PATH/mcp-tools-py" ]; then
    echo "ERROR: mcp-tools-py not found in $MCP_CODER_VENV_PATH"
    echo "Please reinstall mcp-coder: pip install mcp-coder"
    exit 1
fi
if [ ! -x "$MCP_CODER_VENV_PATH/mcp-workspace" ]; then
    echo "ERROR: mcp-workspace not found in $MCP_CODER_VENV_PATH"
    echo "Please reinstall mcp-coder: pip install mcp-coder"
    exit 1
fi

# === Step 4b: Print MCP server versions ===
"$MCP_CODER_VENV_PATH/mcp-workspace" --version
"$MCP_CODER_VENV_PATH/mcp-tools-py" --version

# === Step 5: Set env vars and launch ===
export MCP_CODER_VENV_PATH
export MCP_CODER_VENV_DIR
export MCP_CODER_PROJECT_DIR="$PWD"
export DISABLE_AUTOUPDATER=1
export PATH="$MCP_CODER_VENV_PATH:$PATH"

# === Step 6: Platform-specific MCP config override ===
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

echo "Starting Claude Code with:"
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
