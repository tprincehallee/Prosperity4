"""
P3 Round 2 product config — adds Croissants, Jams, Djembes, Picnic Baskets.

Copy the PRODUCT_CONFIG dict into trader.py when testing against P3 Round 2 data.

New products:
  CROISSANTS, JAMS, DJEMBES — component ETFs. Market-make individually.
  PICNIC_BASKET1 = 6×CROISSANTS + 3×JAMS + 1×DJEMBES (position limit 60)
  PICNIC_BASKET2 = 4×CROISSANTS + 2×JAMS (position limit 100)
  Both baskets use pairs_arb to exploit basket-NAV spread deviations.
"""

PRODUCT_CONFIG = {
    # Round 1 products
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
    # Round 2 products
    "CROISSANTS": {
        "strategy": "market_make_ema",
        "position_limit": 250,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 0.8,
    },
    "JAMS": {
        "strategy": "market_make_ema",
        "position_limit": 350,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 0.8,
    },
    "DJEMBES": {
        "strategy": "market_make_ema",
        "position_limit": 60,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 0.8,
    },
    "PICNIC_BASKET1": {
        "strategy": "pairs_arb",
        "position_limit": 60,
        "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
        "z_entry": 2.0,
        "z_exit": 0.5,
        "spread_window": 50,
        "max_order_size": 10,
    },
    "PICNIC_BASKET2": {
        "strategy": "pairs_arb",
        "position_limit": 100,
        "components": {"CROISSANTS": 4, "JAMS": 2},
        "z_entry": 2.0,
        "z_exit": 0.5,
        "spread_window": 50,
        "max_order_size": 15,
    },
}
