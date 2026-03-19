"""
P3 Round 1 product config — Rainforest Resin, Kelp, Squid Ink.

Copy the PRODUCT_CONFIG dict into trader.py when testing against P3 Round 1 data.

Products:
  RAINFOREST_RESIN — fixed fair value at 10,000. Pure market making.
  KELP            — random walk. EMA-based market making.
  SQUID_INK       — random walk with bot signals. EMA market making by default;
                    upgrade to informed_trader once bot IDs are identified.
"""

PRODUCT_CONFIG = {
    "RAINFOREST_RESIN": {
        "strategy": "market_make_fixed",
        "position_limit": 50,
        "fair_value": 10000,
        "spread": 2,
        "skew_factor": 1.0,
    },
    "KELP": {
        "strategy": "market_make_ema",
        "position_limit": 50,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 1.0,
    },
    "SQUID_INK": {
        "strategy": "market_make_ema",
        "position_limit": 50,
        "ema_alpha": 0.2,
        "spread": 3,
        "skew_factor": 1.0,
    },
}
