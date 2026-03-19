"""
P3 Round 5 product config — adds Magnificent Macarons (cross-exchange arb).

Copy the PRODUCT_CONFIG dict into trader.py when testing against P3 Round 5 data.

New products:
  MAGNIFICENT_MACARONS — tradeable locally and on a foreign exchange via conversions.
                         implied_bid = obs.bidPrice - exportTariff - transportFees - storageCost
                         implied_ask = obs.askPrice + importTariff + transportFees
                         Exploit when local price crosses implied foreign price.

Key insight from P3:
  A hidden "taker bot" aggressively buys/sells near certain price levels in Macarons.
  Detecting this pattern (from market_trades buyer/seller IDs) is extremely high-alpha.
  Once identified, switch SQUID_INK (or Macarons) to informed_trader strategy.

  Example: uncomment the SQUID_INK override below once "Olivia" (or equivalent)
  is confirmed as the informed trader for that product this round.
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
    # Uncomment and replace "Olivia" with the actual informed trader ID once identified:
    # "SQUID_INK": {
    #     "strategy": "informed_trader",
    #     "position_limit": 50,
    #     "tracked_traders": ["Olivia"],
    #     "flow_window": 10,
    #     "signal_threshold": 5,
    #     "base_spread": 2,
    #     "ema_alpha": 0.3,
    # },

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
    # Round 4 products
    "VOLCANIC_ROCK": {
        "strategy": "market_make_ema",
        "position_limit": 400,
        "ema_alpha": 0.2,
        "spread": 3,
        "skew_factor": 0.5,
    },
    "VOLCANIC_ROCK_VOUCHER_9500": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 9500,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
        "max_order_size": 20,
    },
    "VOLCANIC_ROCK_VOUCHER_9750": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 9750,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
        "max_order_size": 20,
    },
    "VOLCANIC_ROCK_VOUCHER_10000": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 10000,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
        "max_order_size": 20,
    },
    "VOLCANIC_ROCK_VOUCHER_10250": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 10250,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
        "max_order_size": 20,
    },
    "VOLCANIC_ROCK_VOUCHER_10500": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 10500,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
        "max_order_size": 20,
    },
    # Round 5 products
    "MAGNIFICENT_MACARONS": {
        "strategy": "cross_exchange",
        "position_limit": 75,
        "conversion_product": "MAGNIFICENT_MACARONS",
        "storage_cost": 0.1,
        "spread_buffer": 1.0,
        "max_conversion": 10,
    },
}
