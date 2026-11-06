@echo off
REM Generate dependency graph using pydeps
REM Usage: tools\pydeps_graph.bat
REM
REM Creates:
REM   - docs/architecture/pydeps_graph.svg (requires GraphViz)
REM   - docs/architecture/pydeps_graph.dot (always created)
REM
REM Options used:
REM   --max-bacon 2      : Show modules up to 2 hops away
REM   --cluster          : Group modules by package
REM   --rankdir TB       : Top-to-bottom layout
REM   --noshow           : Don't auto-open the result
REM   -x tests.*         : Exclude test modules
REM
REM Note: For SVG output, install GraphViz from https://graphviz.org/download/

where pydeps >nul 2>&1
if errorlevel 1 (
    echo ERROR: pydeps not found. Install with: pip install pydeps
    exit /b 1
)

echo Generating dependency graph with pydeps...

REM Ensure output directory exists
if not exist "docs\architecture" mkdir "docs\architecture"

REM Always generate DOT file (no GraphViz needed)
echo Creating DOT file...
pydeps src/mcp_workspace --max-bacon 2 --cluster --rankdir TB --no-output --show-dot > docs/architecture/pydeps_graph.dot 2>&1

REM Try to generate SVG (requires GraphViz)
echo Creating SVG file (requires GraphViz)...
pydeps src/mcp_workspace --max-bacon 2 --cluster --rankdir TB --noshow -x "tests.*" -o docs/architecture/pydeps_graph.svg 2>nul

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Created: docs/architecture/pydeps_graph.svg
    echo Created: docs/architecture/pydeps_graph.dot
    echo.
    echo To view SVG: start docs\architecture\pydeps_graph.svg
) else (
    echo.
    echo Created: docs/architecture/pydeps_graph.dot
    echo.
    echo SVG generation failed - GraphViz not installed.
    echo Install from: https://graphviz.org/download/
)
