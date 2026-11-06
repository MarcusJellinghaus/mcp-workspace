@echo off
echo ============================================
echo   Environment Check - mcp-workspace
echo ============================================
echo.
echo --- Version Control ---
git --version
gh --version
echo.
echo --- Python Environment ---
python -c "import sys; print('Python:', sys.version)"
python -c "import sys; print('Executable:', sys.executable)"
python -c "import sys, os; print('Environment:', os.path.dirname(sys.executable))"
pip --version
echo.
echo --- Formatting ---
ruff version
echo.
echo --- Linting and Quality ---
pylint --version
mypy --version
vulture --version
echo.
echo --- Testing ---
pytest --version
echo.
echo --- Architecture and Dependencies ---
tach --version
lint-imports --version
deptry --version
echo.
echo --- Optional Tools ---
mlflow --version
uv --version
echo.
echo --- MCP Servers ---
mcp-tools-py --version
mcp-workspace --version
mcp-coder --version
echo.
echo ============================================
echo   Done
echo ============================================
