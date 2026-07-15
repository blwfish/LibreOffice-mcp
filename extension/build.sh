#!/usr/bin/env bash
# Packages this directory into dist/lo-mcp.oxt (a plain zip file).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ../dist
rm -f ../dist/lo-mcp.oxt
zip -rX ../dist/lo-mcp.oxt META-INF description.xml Addons.xcu Jobs.xcu pythonpath -x '*.pyc' -x '__pycache__/*'
echo "built dist/lo-mcp.oxt"
