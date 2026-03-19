"""
P3 Round 4 product config — adds Volcanic Rock and Call Vouchers (options).

Copy the PRODUCT_CONFIG dict into trader.py when testing against P3 Round 4 data.

New products:
  VOLCANIC_ROCK              — underlying; market-make with EMA.
  VOLCANIC_ROCK_VOUCHER_*    — call options at strikes 9500/9750/10000/10250/10500.
                               Priced via Black-Scholes; trade IV mean reversion.
                               Delta hedged against VOLCANIC_ROCK.
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
}
