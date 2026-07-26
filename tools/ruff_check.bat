@echo off
REM Check docstrings using ruff (D + DOC rules)
REM
REM Usage from cmd.exe: tools\ruff_check.bat

where ruff >nul 2>&1
if errorlevel 1 (
    echo ERROR: ruff not found. Install with: uv pip install ruff
    exit /b 1
)

echo Checking docstrings with ruff...
ruff check src tests %*
exit /b %ERRORLEVEL%
