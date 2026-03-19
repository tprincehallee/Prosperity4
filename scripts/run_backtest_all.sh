#!/bin/bash
# Run backtests across all rounds and summarize results
set -e

python scripts/merge_to_submission.py

# Try to detect backtester
if command -v prosperity4bt &> /dev/null; then
    BT="prosperity4bt"
elif command -v prosperity3bt &> /dev/null; then
    BT="prosperity3bt"
else
    echo "ERROR: No backtester found."
    exit 1
fi

echo "=== Running all rounds ==="
for round in 0 1 2 3 4 5; do
    echo "--- Round $round ---"
    $BT trader.py $round 2>/dev/null || echo "  (no data for round $round)"
    echo ""
done
