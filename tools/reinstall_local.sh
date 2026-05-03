#!/bin/bash
# Reinstall mcp-workspace package in development mode (editable install)
# Usage: source tools/reinstall_local.sh   (from project root; persists venv activation)
#    or: bash tools/reinstall_local.sh     (does not persist activation to caller)

# Detect if script is sourced (return works only in sourced/function context)
(return 0 2>/dev/null) && _SOURCED=1 || _SOURCED=0

echo "============================================="
echo "MCP-Workspace Package Reinstallation"
echo "============================================="
echo ""

# Determine project root (parent of tools directory)
_SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
_SCRIPT_DIR="$( cd "$( dirname "$_SCRIPT_PATH" )" && pwd )"
PROJECT_DIR="$( cd "$_SCRIPT_DIR/.." && pwd )"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_BIN="$VENV_DIR/bin"
PY="$VENV_BIN/python"

# Silently deactivate any active venv (will reactivate correct one at end)
if command -v deactivate >/dev/null 2>&1; then
    deactivate 2>/dev/null || true
fi

echo "[0/6] Checking Python environment..."

if ! command -v uv >/dev/null 2>&1; then
    echo "[FAIL] uv not found. Install it: pip install uv"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] uv found"

if [ ! -f "$VENV_BIN/activate" ]; then
    echo "Local virtual environment not found at $VENV_DIR"
    ( cd "$PROJECT_DIR" && uv venv .venv )
    echo "Local virtual environment created at $VENV_DIR"
fi
echo "[OK] Target environment: $VENV_DIR"
echo ""

echo "[1/6] Uninstalling existing packages..."
uv pip uninstall mcp-workspace mcp-coder-utils mcp-config-tool mcp-tools-py mcp-coder --python "$PY" 2>/dev/null || true
echo "[OK] Packages uninstalled"

echo ""
echo "[2/6] Installing mcp-workspace (this project) in editable mode..."
# Editable install pulls all deps (including mcp-tools-py,
# mcp-coder-utils) from PyPI first.
if ! ( cd "$PROJECT_DIR" && uv pip install -e ".[dev]" --python "$PY" ); then
    echo "[FAIL] Installation failed!"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] Package and dev dependencies installed"

echo ""
echo "[3/6] Overriding dependencies with GitHub versions..."
# Validate read_github_deps.py succeeds before parsing its output
if ! "$PY" "$PROJECT_DIR/tools/read_github_deps.py" >/dev/null 2>&1; then
    echo "[FAIL] read_github_deps.py failed!"
    "$PY" "$PROJECT_DIR/tools/read_github_deps.py"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
# Read GitHub dependency overrides from pyproject.toml
while IFS= read -r CMD; do
    [ -z "$CMD" ] && continue
    echo "  $CMD"
    if ! eval "$CMD --python \"$PY\""; then
        echo "[FAIL] GitHub dependency override failed!"
        [ "$_SOURCED" = "1" ] && return 1 || exit 1
    fi
done < <("$PY" "$PROJECT_DIR/tools/read_github_deps.py")
echo "[OK] GitHub dependencies overridden from pyproject.toml"

echo ""
echo "[4/6] Reinstalling local package (editable)..."
if ! ( cd "$PROJECT_DIR" && uv pip install -e . --python "$PY" ); then
    echo "[FAIL] Local editable reinstall failed!"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] Local editable install takes precedence"

echo ""
echo "[5/6] Verifying import and CLI entry point..."
if ! "$PY" -c "import mcp_workspace; print('OK')"; then
    echo "[FAIL] Import verification failed!"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] mcp_workspace import verified"

if ! "$VENV_BIN/mcp-workspace" --help >/dev/null 2>&1; then
    echo "[FAIL] mcp-workspace CLI verification failed!"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] mcp-workspace CLI works"

echo ""
echo "============================================="
echo "[6/6] Reinstallation completed successfully!"
echo ""
echo "Entry point installed in: $VENV_BIN"
echo "  - mcp-workspace"
echo "============================================="
echo ""

# Activate the correct venv (only persists if this script was sourced)
if [ -n "${VIRTUAL_ENV:-}" ] && [ "$VIRTUAL_ENV" != "$VENV_DIR" ]; then
    echo "  Deactivating wrong virtual environment: $VIRTUAL_ENV"
    deactivate 2>/dev/null || true
fi

if [ "${VIRTUAL_ENV:-}" != "$VENV_DIR" ]; then
    echo "  Activating virtual environment: $VENV_DIR"
    # shellcheck disable=SC1090,SC1091
    source "$VENV_BIN/activate"
fi

if [ "$_SOURCED" != "1" ]; then
    echo ""
    echo "Note: Activation does not persist because this script was not sourced."
    echo "      To activate in your current shell, run:"
    echo "        source $VENV_BIN/activate"
    echo "      Or source this script next time:"
    echo "        source tools/reinstall_local.sh"
fi

unset _SOURCED _SCRIPT_PATH _SCRIPT_DIR
