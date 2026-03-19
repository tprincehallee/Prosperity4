"""
Shared mock factories for strategy tests.
"""

import json
import sys
import os

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
import trader as trader_module
from trader import Trader


def make_order_depth(bids: dict, asks: dict) -> OrderDepth:
    """
    Build an OrderDepth from human-friendly dicts.

    Args:
        bids: {price: positive_qty, ...}
        asks: {price: positive_qty, ...}  (stored as negative internally)
    """
    od = OrderDepth()
    od.buy_orders = dict(bids)
    od.sell_orders = {p: -q for p, q in asks.items()}
    return od


def make_trade(
    symbol: str,
    price: int,
    qty: int,
    buyer: str = "",
    seller: str = "",
    timestamp: int = 0,
) -> Trade:
    return Trade(symbol, price, qty, buyer, seller, timestamp)


def make_state(
    order_depths=None,
    market_trades=None,
    position=None,
    observations=None,
    trader_data="",
    timestamp=0,
) -> TradingState:
    """Build a complete TradingState from compact arguments."""
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


def run_trader(state, product_config=None):
    """
    Create a Trader, optionally override PRODUCT_CONFIG, and run one timestep.

    Returns (result, conversions, traderData).
    """
    original_config = trader_module.PRODUCT_CONFIG
    try:
        if product_config is not None:
            trader_module.PRODUCT_CONFIG = product_config
        t = Trader()
        return t.run(state)
    finally:
        trader_module.PRODUCT_CONFIG = original_config
