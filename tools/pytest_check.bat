@echo off
REM Run pytest

echo Running pytest (parallel mode)...
pytest -n auto

if %errorlevel% neq 0 (
    echo.
    echo ✗ Tests failed!
    exit /b 1
)

echo Running performance tests (serial)...
pytest -n 0 -m performance

if %errorlevel% neq 0 (
    echo.
    echo ✗ Performance tests failed!
    exit /b 1
)

echo.
echo ✓ All tests passed!
