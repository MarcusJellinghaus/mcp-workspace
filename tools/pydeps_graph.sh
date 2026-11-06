#!/usr/bin/env bash
# Generate dependency graph using pydeps
# Usage: tools/pydeps_graph.sh
#
# Creates:
#   - docs/architecture/pydeps_graph.svg (requires GraphViz)
#   - docs/architecture/pydeps_graph.dot (always created)
#
# Options used:
#   --max-bacon 2      : Show modules up to 2 hops away
#   --cluster          : Group modules by package
#   --rankdir TB       : Top-to-bottom layout
#   --noshow           : Don't auto-open the result
#   -x tests.*         : Exclude test modules
#
# Note: For SVG output, install GraphViz from https://graphviz.org/download/

set -e

if ! command -v pydeps &> /dev/null; then
    echo "ERROR: pydeps not found. Install with: pip install pydeps"
    exit 1
fi

echo "Generating dependency graph with pydeps..."

# Ensure output directory exists
mkdir -p docs/architecture

# Always generate DOT file (no GraphViz needed)
echo "Creating DOT file..."
pydeps src/mcp_workspace --max-bacon 2 --cluster --rankdir TB --no-output --show-dot > docs/architecture/pydeps_graph.dot 2>&1 || true

# Try to generate SVG (requires GraphViz)
echo "Creating SVG file (requires GraphViz)..."
if pydeps src/mcp_workspace --max-bacon 2 --cluster --rankdir TB --noshow -x "tests.*" -o docs/architecture/pydeps_graph.svg 2>/dev/null; then
    echo ""
    echo "Created: docs/architecture/pydeps_graph.svg"
    echo "Created: docs/architecture/pydeps_graph.dot"
    echo ""
    echo "To view: open docs/architecture/pydeps_graph.svg"
else
    echo ""
    echo "Created: docs/architecture/pydeps_graph.dot"
    echo ""
    echo "SVG generation failed - GraphViz not installed."
    echo "Install from: https://graphviz.org/download/"
fi
