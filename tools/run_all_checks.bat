@echo off
REM Run all code quality and architecture checks

echo ========================================
echo Running All Code Quality Checks
echo ========================================
echo.

echo [1/6] Running black...
call tools\format_all.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [2/6] Running pylint...
call tools\pylint_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [3/6] Running mypy...
call tools\mypy_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [4/6] Running pytest...
call tools\pytest_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo ========================================
echo Running Architecture Checks
echo ========================================
echo.

echo [5/6] Running import-linter...
call tools\lint_imports.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [6/6] Running tach...
call tools\tach_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo ========================================
echo ✓ ALL CHECKS PASSED!
echo ========================================
