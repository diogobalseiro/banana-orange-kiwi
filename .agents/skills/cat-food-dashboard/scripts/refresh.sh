#!/usr/bin/env bash
set -e

# Change to repository root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../../.." >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=== Cat Food Ranking: Full Refresh ==="
python3 refresh.py --retailer continente --type all "$@"
echo "=== Refresh Complete! ==="
