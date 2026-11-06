#!/bin/bash
# Check dependency declarations using deptry
#
# Usage from Git Bash: ./tools/deptry_check.sh

if ! command -v deptry &> /dev/null; then
    echo "ERROR: deptry not found. Install with: uv pip install deptry"
    exit 1
fi

echo "Checking dependency declarations..."
deptry src "$@"
