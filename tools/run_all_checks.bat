@echo off
REM Run all code quality and architecture checks

echo ========================================
echo Running All Code Quality Checks
echo ========================================
echo.

echo [1/9] Running ruff import sort and format...
ruff check --select I --fix src tests tools
if %errorlevel% neq 0 exit /b 1
ruff format src tests tools
if %errorlevel% neq 0 exit /b 1
echo.

echo [2/9] Running ruff lint...
call tools\ruff_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [3/9] Running pylint...
call tools\pylint_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [4/9] Running mypy...
call tools\mypy.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [5/9] Running pytest...
call tools\pytest_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo ========================================
echo Running Architecture Checks
echo ========================================
echo.

echo [6/9] Running import-linter...
call tools\lint_imports.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [7/9] Running tach...
call tools\tach_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [8/9] Running vulture...
call tools\vulture_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo [9/9] Running deptry...
call tools\deptry_check.bat
if %errorlevel% neq 0 exit /b 1
echo.

echo ========================================
echo ✓ ALL CHECKS PASSED!
echo ========================================
