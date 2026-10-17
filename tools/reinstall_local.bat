@echo off
setlocal enabledelayedexpansion
REM Reinstall mcp-workspace package in development mode
REM Usage: call tools\reinstall_local.bat  (from project root)
echo =============================================
echo MCP-Workspace Package Reinstallation
echo =============================================
echo.

REM Determine project root (parent of tools directory)
set "PROJECT_DIR=%~dp0.."
pushd "!PROJECT_DIR!"
set "PROJECT_DIR=%CD%"
popd

set "VENV_DIR=!PROJECT_DIR!\.venv"
set "VENV_SCRIPTS=!VENV_DIR!\Scripts"

REM Silently deactivate any active venv (will reactivate correct one at end)
call deactivate 2>nul

echo [0/6] Checking Python environment...

REM Check if uv is available
where uv >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [FAIL] uv not found. Install it: pip install uv
    exit /b 1
)
echo [OK] uv found

REM Check if local .venv exists
if not exist "!VENV_SCRIPTS!\activate.bat" (
    echo Local virtual environment not found at !VENV_DIR!
    uv venv .venv
    echo Local virtual environment created at !VENV_DIR!
)
echo [OK] Target environment: !VENV_DIR!
echo.

echo [1/6] Uninstalling existing packages...
uv pip uninstall mcp-workspace mcp-coder-utils mcp-tools-py mcp-coder --python "!VENV_SCRIPTS!\python.exe" 2>nul
echo [OK] Packages uninstalled

echo.
echo [2/6] Installing mcp-workspace (this project) in editable mode...
REM Editable install pulls all deps (including mcp-tools-py,
REM mcp-coder-utils) from PyPI first.
pushd "!PROJECT_DIR!"
uv pip install -e ".[dev]" --python "!VENV_SCRIPTS!\python.exe"
if !ERRORLEVEL! NEQ 0 (
    echo [FAIL] Installation failed!
    popd
    exit /b 1
)
popd
echo [OK] Package and dev dependencies installed

echo.
echo [3/6] Overriding dependencies with GitHub versions...
REM Validate read_github_deps.py succeeds before parsing its output
"!VENV_SCRIPTS!\python.exe" tools\read_github_deps.py > nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [FAIL] read_github_deps.py failed!
    "!VENV_SCRIPTS!\python.exe" tools\read_github_deps.py
    exit /b 1
)
REM Read GitHub dependency overrides from pyproject.toml
for /f "delims=" %%C in ('"!VENV_SCRIPTS!\python.exe" tools\read_github_deps.py') do (
    echo   %%C
    %%C --python "!VENV_SCRIPTS!\python.exe"
    if !ERRORLEVEL! NEQ 0 (
        echo [FAIL] GitHub dependency override failed!
        exit /b 1
    )
)
echo [OK] GitHub dependencies overridden from pyproject.toml

echo.
echo [4/6] Reinstalling local package (editable)...
pushd "!PROJECT_DIR!"
uv pip install -e . --python "!VENV_SCRIPTS!\python.exe"
if !ERRORLEVEL! NEQ 0 (
    echo [FAIL] Local editable reinstall failed!
    popd
    exit /b 1
)
popd
echo [OK] Local editable install takes precedence

echo.
echo [5/6] Verifying import and CLI entry point...
"!VENV_SCRIPTS!\python.exe" -c "import mcp_workspace; print('OK')"
if !ERRORLEVEL! NEQ 0 (
    echo [FAIL] Import verification failed!
    exit /b 1
)
echo [OK] mcp_workspace import verified

"!VENV_SCRIPTS!\mcp-workspace.exe" --help >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [FAIL] mcp-workspace CLI verification failed!
    exit /b 1
)
echo [OK] mcp-workspace CLI works

echo.
echo =============================================
echo [6/6] Reinstallation completed successfully!
echo.
echo Entry point installed in: !VENV_SCRIPTS!
echo   - mcp-workspace.exe
echo =============================================
echo.

REM [6/6] Pass VENV_DIR out of setlocal scope so activation persists to caller
endlocal & set "_REINSTALL_VENV=%VENV_DIR%"

REM Deactivate wrong venv if one is active
if defined VIRTUAL_ENV (
    if not "%VIRTUAL_ENV%"=="%_REINSTALL_VENV%" (
        echo   Deactivating wrong virtual environment: %VIRTUAL_ENV%
        call deactivate 2>nul
    )
)

REM Activate the correct venv (persists to caller's shell)
if not "%VIRTUAL_ENV%"=="%_REINSTALL_VENV%" (
    echo   Activating virtual environment: %_REINSTALL_VENV%
    call "%_REINSTALL_VENV%\Scripts\activate.bat"
)

set "_REINSTALL_VENV="
