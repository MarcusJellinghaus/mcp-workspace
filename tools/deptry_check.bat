@echo off
REM Check dependency declarations using deptry
REM
REM Usage from cmd.exe: tools\deptry_check.bat

where deptry >nul 2>&1
if errorlevel 1 (
    echo ERROR: deptry not found. Install with: uv pip install deptry
    exit /b 1
)

echo Checking dependency declarations...
deptry src %*
exit /b %ERRORLEVEL%
