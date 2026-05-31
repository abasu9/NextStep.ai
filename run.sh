#!/usr/bin/env bash
# Local preview of the GitHub Pages site (same as production)
set -euo pipefail
cd "$(dirname "$0")/docs"
echo "NextStep.ai → http://localhost:8080"
exec python3 -m http.server 8080
