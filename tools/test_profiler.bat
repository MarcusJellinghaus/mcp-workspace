@echo off
REM ============================================================================
REM Test Profiler - Profile all pytest tests and generate reports for slow ones
REM ============================================================================

echo.
echo === Test Profiler Starting ===
echo.

REM Step 1: Clean the performance data directory
echo [1/4] Cleaning performance data directory...
if exist "docs\tests\performance_data\prof" (
    rd /s /q "docs\tests\performance_data\prof"
)
mkdir "docs\tests\performance_data\prof"
echo Done.
echo.

REM Step 2: Run pytest with profiling plugin (single pass, no parallel)
echo [2/4] Running pytest with profiling (this may take a while)...
echo This will profile ALL tests individually in a single run.
echo.

REM Add current directory to PYTHONPATH so pytest can import tools package
set PYTHONPATH=%CD%;%PYTHONPATH%

pytest -n0 -p tools.test_profiler_plugin -v
set PYTEST_EXIT_CODE=%errorlevel%

if %PYTEST_EXIT_CODE% neq 0 (
    echo.
    echo WARNING: Some tests failed ^(exit code: %PYTEST_EXIT_CODE%^)
    echo Continuing to generate reports for completed tests...
) else (
    echo.
    echo Pytest run complete - all tests passed.
)
echo.

REM Step 3: Generate text reports for slow tests (>1s)
echo [3/4] Generating reports for slow tests...
python tools\test_profiler_plugin\generate_report.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Report generation failed!
    exit /b %errorlevel%
)
echo.

REM Step 4: Display summary
echo [4/4] Profiling complete!
echo.
echo === Test Profiler Complete ===
echo Output directory: docs\tests\performance_data\prof
echo.
echo Files generated:
echo   - *.prof files for ALL tests
echo   - *_report.txt for tests taking ^>1 second
echo   - summary.txt with overview
echo   - durations.json with all test timings
echo.

REM Exit with pytest's original exit code
if %PYTEST_EXIT_CODE% neq 0 (
    echo Note: Script completed but some tests failed.
    exit /b %PYTEST_EXIT_CODE%
)
