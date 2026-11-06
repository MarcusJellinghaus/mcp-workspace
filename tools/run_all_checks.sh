#!/bin/bash
# Run all code quality and architecture checks
set -e

echo "========================================"
echo "Running All Code Quality Checks"
echo "========================================"
echo ""

echo "[1/9] Running ruff import sort and format..."
ruff check --select I --fix src tests tools
ruff format src tests tools
echo ""

echo "[2/9] Running ruff lint..."
ruff check src tests tools
echo ""

echo "[3/9] Running pylint..."
pylint ./src ./tests
echo ""

echo "[4/9] Running mypy..."
mypy --strict src tests
echo ""

echo "[5/9] Running pytest..."
pytest -n auto
echo ""

echo "========================================"
echo "Running Architecture Checks"
echo "========================================"
echo ""

echo "[6/9] Running import-linter..."
./tools/lint_imports.sh
echo ""

echo "[7/9] Running tach..."
./tools/tach_check.sh
echo ""

echo "[8/9] Running vulture..."
./tools/vulture_check.sh
echo ""

echo "[9/9] Running deptry..."
./tools/deptry_check.sh
echo ""

echo "========================================"
echo "✓ ALL CHECKS PASSED!"
echo "========================================"
