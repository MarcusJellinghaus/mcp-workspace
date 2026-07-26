#!/bin/bash
# Check docstrings using ruff (D + DOC rules)
#
# Usage from Git Bash: ./tools/ruff_check.sh

if ! command -v ruff &> /dev/null; then
    echo "ERROR: ruff not found. Install with: uv pip install ruff"
    exit 1
fi

echo "Checking docstrings with ruff..."
ruff check src tests "$@"
