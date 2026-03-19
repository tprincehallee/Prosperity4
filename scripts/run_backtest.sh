#!/bin/bash
# Usage: ./scripts/run_backtest.sh [round] [day]
# Defaults to round 0, all days
# Runs the submission checker first, then the backtester

set -e

ROUND=${1:-0}
DAY=${2:-""}

echo "=== Pre-submission check ==="
python scripts/merge_to_submission.py

echo ""
echo "=== Running backtest: round $ROUND ==="

# Try prosperity4bt first, fall back to prosperity3bt
if command -v prosperity4bt &> /dev/null; then
    BT="prosperity4bt"
elif command -v prosperity3bt &> /dev/null; then
    BT="prosperity3bt"
else
    echo "ERROR: No backtester found. Install with: pip install -U prosperity3bt"
    exit 1
fi

if [ -z "$DAY" ]; then
    $BT trader.py $ROUND
else
    $BT trader.py $ROUND --day $DAY
fi
