"""
Tests for strategy_pairs_arb, strategy_informed_trader, strategy_cross_exchange.

Run with:
    python tests/test_strategies.py
"""

import sys
import os
import json

# Add repo root to path so we can import trader and datamodel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datamodel import (
    Order,
    OrderDepth,
    Trade,
    TradingState,
    Observation,
    ConversionObservation,
    Listing,
)
from trader import Trader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_order_depth(bids: dict, asks: dict) -> OrderDepth:
    """
    bids = {price: positive_qty}
    asks = {price: positive_qty}  (stored as negative internally)
    """
    od = OrderDepth()
    od.buy_orders = dict(bids)
    od.sell_orders = {p: -q for p, q in asks.items()}
    return od


def make_state(
    order_depths=None,
    market_trades=None,
    position=None,
    observations=None,
    trader_data="",
    timestamp=0,
) -> TradingState:
    od = order_depths or {}
    listings = {sym: Listing(sym, sym, "SEASHELLS") for sym in od}
    return TradingState(
        traderData=trader_data,
        timestamp=timestamp,
        listings=listings,
        order_depths=od,
        own_trades={},
        market_trades=market_trades or {},
        position=position or {},
        observations=observations or Observation(),
    )


# ---------------------------------------------------------------------------
# Pairs Arb Tests
# ---------------------------------------------------------------------------

def test_pairs_arb_overpriced():
    """
    Basket overpriced (z > z_entry): strategy should sell basket.

    Setup:
        basket_mid = 103  (bid=102, ask=104)
        CROISSANTS mid = 10, JAMS mid = 10, DJEMBES mid = 10
        NAV = 6*10 + 3*10 + 1*10 = 100
        spread = 103 - 100 = 3
        spread_history = [0.0]*49 → after append, z ≈ 7 >> z_entry=2.0
    """
    basket_od = make_order_depth({102: 10}, {104: 10})
    croissants_od = make_order_depth({9: 20}, {11: 20})
    jams_od = make_order_depth({9: 30}, {11: 30})
    djembes_od = make_order_depth({9: 10}, {11: 10})

    # Pre-populate spread history so z is well above threshold
    spread_history = [0.0] * 49
    trader_data = json.dumps({
        "PICNIC_BASKET1": {"spread_history": spread_history}
    })

    state = make_state(
        order_depths={
            "PICNIC_BASKET1": basket_od,
            "CROISSANTS": croissants_od,
            "JAMS": jams_od,
            "DJEMBES": djembes_od,
        },
        position={"PICNIC_BASKET1": 0},
        trader_data=trader_data,
    )

    config = {
        "strategy": "pairs_arb",
        "position_limit": 60,
        "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
        "z_entry": 2.0,
        "z_exit": 0.5,
        "spread_window": 50,
        "max_order_size": 10,
    }

    trader = Trader()
    trader.state_data = trader._load_state(trader_data)
    orders, conv = trader.strategy_pairs_arb("PICNIC_BASKET1", state, config, 0, 60)

    sell_orders = [o for o in orders if o.quantity < 0]
    assert len(sell_orders) > 0, f"Expected sell orders for overpriced basket, got: {orders}"
    assert all(o.symbol == "PICNIC_BASKET1" for o in orders), \
        "All returned orders should be for basket (component orders go to _component_orders)"
    assert conv == 0
    # Verify component buy orders were accumulated
    assert "CROISSANTS" in trader._component_orders, "Expected CROISSANTS component orders"
    assert "JAMS" in trader._component_orders, "Expected JAMS component orders"
    assert "DJEMBES" in trader._component_orders, "Expected DJEMBES component orders"
    print("PASS: test_pairs_arb_overpriced")


def test_pairs_arb_underpriced():
    """
    Basket underpriced (z < -z_entry): strategy should buy basket.

    Setup:
        basket_mid = 97  (bid=96, ask=98)
        NAV = 100 (same component mids as above)
        spread = 97 - 100 = -3 → z ≈ -7 << -z_entry=-2.0
    """
    basket_od = make_order_depth({96: 10}, {98: 10})
    croissants_od = make_order_depth({9: 20}, {11: 20})
    jams_od = make_order_depth({9: 30}, {11: 30})
    djembes_od = make_order_depth({9: 10}, {11: 10})

    spread_history = [0.0] * 49
    trader_data = json.dumps({
        "PICNIC_BASKET1": {"spread_history": spread_history}
    })

    state = make_state(
        order_depths={
            "PICNIC_BASKET1": basket_od,
            "CROISSANTS": croissants_od,
            "JAMS": jams_od,
            "DJEMBES": djembes_od,
        },
        position={"PICNIC_BASKET1": 0},
        trader_data=trader_data,
    )

    config = {
        "strategy": "pairs_arb",
        "position_limit": 60,
        "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
        "z_entry": 2.0,
        "z_exit": 0.5,
        "spread_window": 50,
        "max_order_size": 10,
    }

    trader = Trader()
    trader.state_data = trader._load_state(trader_data)
    orders, conv = trader.strategy_pairs_arb("PICNIC_BASKET1", state, config, 0, 60)

    buy_orders = [o for o in orders if o.quantity > 0]
    assert len(buy_orders) > 0, f"Expected buy orders for underpriced basket, got: {orders}"
    assert conv == 0
    print("PASS: test_pairs_arb_underpriced")


def test_pairs_arb_unwind():
    """
    |z| < z_exit and position != 0: strategy should unwind.

    Setup:
        basket_mid = 100.5  (bid=100, ask=101)
        NAV = 100 → spread = 0.5
        spread_history = [0.5]*49 → after append, all same → std=0 → z=0 < z_exit=0.5
        position = 5 (long) → should sell to unwind
    """
    basket_od = make_order_depth({100: 10}, {101: 10})
    croissants_od = make_order_depth({9: 20}, {11: 20})
    jams_od = make_order_depth({9: 30}, {11: 30})
    djembes_od = make_order_depth({9: 10}, {11: 10})

    # All values the same → z=0 when appended
    spread_history = [0.5] * 49
    trader_data = json.dumps({
        "PICNIC_BASKET1": {"spread_history": spread_history}
    })

    state = make_state(
        order_depths={
            "PICNIC_BASKET1": basket_od,
            "CROISSANTS": croissants_od,
            "JAMS": jams_od,
            "DJEMBES": djembes_od,
        },
        position={"PICNIC_BASKET1": 5},
        trader_data=trader_data,
    )

    config = {
        "strategy": "pairs_arb",
        "position_limit": 60,
        "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
        "z_entry": 2.0,
        "z_exit": 0.5,
        "spread_window": 50,
        "max_order_size": 10,
    }

    trader = Trader()
    trader.state_data = trader._load_state(trader_data)
    orders, conv = trader.strategy_pairs_arb("PICNIC_BASKET1", state, config, 5, 60)

    sell_orders = [o for o in orders if o.quantity < 0]
    assert len(sell_orders) > 0, f"Expected sell orders to unwind long position, got: {orders}"
    assert conv == 0
    print("PASS: test_pairs_arb_unwind")


# ---------------------------------------------------------------------------
# Informed Trader Tests
# ---------------------------------------------------------------------------

def test_informed_trader_buy_signal():
    """
    Olivia has been buying heavily: strategy should aggressively buy.

    Setup:
        flow_history = {"Olivia": [2]*10} → aggregate_flow = 20 > signal_threshold=5
        This timestep: Olivia buys 3 more (appended to history)
        EMA fair value ≈ 100
    """
    od = make_order_depth({99: 10}, {101: 10})

    # Pre-populate flow history with strong buy signal
    flow_history = {"Olivia": [2] * 10}
    trader_data = json.dumps({
        "SQUID_INK": {"ema": 100.0, "flow_history": flow_history}
    })

    trades = [Trade("SQUID_INK", 101, 3, buyer="Olivia", seller="BOT")]
    state = make_state(
        order_depths={"SQUID_INK": od},
        market_trades={"SQUID_INK": trades},
        position={"SQUID_INK": 0},
        trader_data=trader_data,
    )

    config = {
        "strategy": "informed_trader",
        "position_limit": 50,
        "tracked_traders": ["Olivia"],
        "flow_window": 10,
        "signal_threshold": 5,
        "base_spread": 2,
        "ema_alpha": 0.3,
    }

    trader = Trader()
    trader.state_data = trader._load_state(trader_data)
    orders, conv = trader.strategy_informed_trader("SQUID_INK", state, config, 0, 50)

    buy_orders = [o for o in orders if o.quantity > 0]
    assert len(buy_orders) > 0, f"Expected aggressive buy orders, got: {orders}"
    assert conv == 0
    # Aggressive buy: should be taking asks (at ask price or below fv + base_spread)
    assert all(o.price <= 103 for o in buy_orders), \
        "Buy orders should be at ask levels (not passive above fair value)"
    print("PASS: test_informed_trader_buy_signal")


def test_informed_trader_sell_signal():
    """
    Olivia has been selling heavily: strategy should aggressively sell.

    Setup:
        flow_history = {"Olivia": [-2]*10} → aggregate_flow = -20 < -signal_threshold=-5
    """
    od = make_order_depth({99: 10}, {101: 10})

    flow_history = {"Olivia": [-2] * 10}
    trader_data = json.dumps({
        "SQUID_INK": {"ema": 100.0, "flow_history": flow_history}
    })

    trades = [Trade("SQUID_INK", 99, 3, buyer="BOT", seller="Olivia")]
    state = make_state(
        order_depths={"SQUID_INK": od},
        market_trades={"SQUID_INK": trades},
        position={"SQUID_INK": 0},
        trader_data=trader_data,
    )

    config = {
        "strategy": "informed_trader",
        "position_limit": 50,
        "tracked_traders": ["Olivia"],
        "flow_window": 10,
        "signal_threshold": 5,
        "base_spread": 2,
        "ema_alpha": 0.3,
    }

    trader = Trader()
    trader.state_data = trader._load_state(trader_data)
    orders, conv = trader.strategy_informed_trader("SQUID_INK", state, config, 0, 50)

    sell_orders = [o for o in orders if o.quantity < 0]
    assert len(sell_orders) > 0, f"Expected aggressive sell orders, got: {orders}"
    assert conv == 0
    print("PASS: test_informed_trader_sell_signal")


def test_informed_trader_no_signal():
    """
    No signal: strategy should fall back to passive market making.

    Setup:
        flow_history = {"Olivia": [0]*10} → aggregate_flow = 0
        EMA = 100 → bid at 98, ask at 102
    """
    od = make_order_depth({99: 10}, {101: 10})

    flow_history = {"Olivia": [0] * 10}
    trader_data = json.dumps({
        "SQUID_INK": {"ema": 100.0, "flow_history": flow_history}
    })

    state = make_state(
        order_depths={"SQUID_INK": od},
        market_trades={"SQUID_INK": []},
        position={"SQUID_INK": 0},
        trader_data=trader_data,
    )

    config = {
        "strategy": "informed_trader",
        "position_limit": 50,
        "tracked_traders": ["Olivia"],
        "flow_window": 10,
        "signal_threshold": 5,
        "base_spread": 2,
        "ema_alpha": 0.3,
    }

    trader = Trader()
    trader.state_data = trader._load_state(trader_data)
    orders, conv = trader.strategy_informed_trader("SQUID_INK", state, config, 0, 50)

    buy_orders = [o for o in orders if o.quantity > 0]
    sell_orders = [o for o in orders if o.quantity < 0]
    assert len(buy_orders) > 0, f"Expected passive bid order, got: {orders}"
    assert len(sell_orders) > 0, f"Expected passive ask order, got: {orders}"
    # Passive: bid below fair value, ask above fair value
    assert all(o.price <= 100 for o in buy_orders), \
        f"Passive bid should be ≤ fair value 100, got: {[o.price for o in buy_orders]}"
    assert all(o.price >= 100 for o in sell_orders), \
        f"Passive ask should be ≥ fair value 100, got: {[o.price for o in sell_orders]}"
    print("PASS: test_informed_trader_no_signal")


# ---------------------------------------------------------------------------
# Cross Exchange Tests
# ---------------------------------------------------------------------------

def test_cross_exchange_buy_local():
    """
    Implied bid > local ask + spread_buffer: buy locally and return positive conversions.

    Setup:
        obs.bidPrice=103, exportTariff=2, transportFees=1, storage_cost=0
        implied_bid = 103 - 2 - 1 - 0 = 100
        local_ask = 95
        spread_buffer = 1.0
        95 < 100 - 1 = 99 ✓ → arb triggered
    """
    od = make_order_depth({93: 10}, {95: 10})

    obs = ConversionObservation(
        bidPrice=103.0,
        askPrice=108.0,
        transportFees=1.0,
        exportTariff=2.0,
        importTariff=2.0,
    )
    # implied_bid = 103 - 2 - 1 = 100; implied_ask = 108 + 2 + 1 = 111
    observation = Observation(
        plainValueObservations={},
        conversionObservations={"MAGNIFICENT_MACARONS": obs},
    )

    state = make_state(
        order_depths={"MAGNIFICENT_MACARONS": od},
        observations=observation,
        position={"MAGNIFICENT_MACARONS": 0},
    )

    config = {
        "strategy": "cross_exchange",
        "position_limit": 75,
        "conversion_product": "MAGNIFICENT_MACARONS",
        "storage_cost": 0.0,
        "spread_buffer": 1.0,
        "max_conversion": 10,
    }

    trader = Trader()
    trader.state_data = {}
    orders, conv = trader.strategy_cross_exchange(
        "MAGNIFICENT_MACARONS", state, config, 0, 75
    )

    buy_orders = [o for o in orders if o.quantity > 0]
    assert len(buy_orders) > 0, f"Expected buy orders, got: {orders}"
    assert conv > 0, f"Expected positive conversions (export to foreign), got: {conv}"
    # The arb buy should be at the local ask price
    arb_order = buy_orders[0]
    assert arb_order.price == 95, f"Arb buy should be at local ask=95, got: {arb_order.price}"
    print("PASS: test_cross_exchange_buy_local")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_pairs_arb_overpriced()
    test_pairs_arb_underpriced()
    test_pairs_arb_unwind()
    test_informed_trader_buy_signal()
    test_informed_trader_sell_signal()
    test_informed_trader_no_signal()
    test_cross_exchange_buy_local()
    print("\nAll 7 tests passed!")
