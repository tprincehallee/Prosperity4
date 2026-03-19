"""
Comprehensive test suite for all trading strategies.

Run with: python -m pytest tests/test_all_strategies.py -v
"""

import json
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datamodel import (
    Order, OrderDepth, Trade, TradingState, Observation,
    ConversionObservation, Listing,
)
from trader import (
    Trader, clip_orders, bs_call_price, bs_put_price, bs_delta,
    implied_vol, mid_price, best_bid, best_ask,
)
from tests.helpers import make_order_depth, make_trade, make_state, run_trader


# ===================================================================
# Market Making (Fixed) — Tests 1-4
# ===================================================================

class TestMarketMakeFixed:

    def _config(self, **overrides):
        c = {
            "strategy": "market_make_fixed",
            "position_limit": 50,
            "fair_value": 10000,
            "spread": 2,
            "skew_factor": 1.0,
        }
        c.update(overrides)
        return c

    def test_symmetric_quotes_at_zero_inventory(self):
        """1. Quotes symmetrically around fair value at zero inventory."""
        od = make_order_depth({9995: 10}, {10005: 10})
        state = make_state(order_depths={"RESIN": od})
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        orders, conv = trader.strategy_market_make_fixed("RESIN", state, config, 0, 50)
        bids = [o for o in orders if o.quantity > 0 and o.price < 10000]
        asks = [o for o in orders if o.quantity < 0 and o.price > 10000]
        assert len(bids) > 0, "Should place bid below fair value"
        assert len(asks) > 0, "Should place ask above fair value"
        # Symmetric: bid and ask equidistant from fair value
        passive_bid = [o for o in bids if o.price == 9998]
        passive_ask = [o for o in asks if o.price == 10002]
        assert len(passive_bid) > 0, f"Expected bid at 9998, got {[o.price for o in bids]}"
        assert len(passive_ask) > 0, f"Expected ask at 10002, got {[o.price for o in asks]}"

    def test_skews_quotes_when_holding_position(self):
        """2. Skews quotes when holding a long position."""
        od = make_order_depth({9995: 10}, {10005: 10})
        state = make_state(order_depths={"RESIN": od})
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        # Long 25 out of 50 limit → norm_pos = 0.5
        orders, _ = trader.strategy_market_make_fixed("RESIN", state, config, 25, 50)
        passive = [o for o in orders if o.price not in (9995, 10005)]
        bids = [o for o in passive if o.quantity > 0]
        asks = [o for o in passive if o.quantity < 0]
        assert len(bids) > 0 and len(asks) > 0
        # Long position: bid should be wider (lower), ask tighter (closer to fv)
        bid_dist = 10000 - bids[0].price
        ask_dist = asks[0].price - 10000
        assert bid_dist > ask_dist, (
            f"Long position should widen bid more than ask: "
            f"bid_dist={bid_dist}, ask_dist={ask_dist}"
        )

    def test_takes_mispriced_orders(self):
        """3. Takes mispriced asks below fair value and bids above."""
        od = make_order_depth({10001: 5}, {9999: 5})  # bid above fv, ask below fv
        state = make_state(order_depths={"RESIN": od})
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        orders, _ = trader.strategy_market_make_fixed("RESIN", state, config, 0, 50)
        # Should buy the cheap ask at 9999
        buy_9999 = [o for o in orders if o.price == 9999 and o.quantity > 0]
        assert len(buy_9999) > 0, "Should take cheap ask at 9999"
        # Should sell to the expensive bid at 10001
        sell_10001 = [o for o in orders if o.price == 10001 and o.quantity < 0]
        assert len(sell_10001) > 0, "Should take expensive bid at 10001"

    def test_respects_position_limits(self):
        """4. clip_orders prevents exceeding position limits."""
        orders = [
            Order("RESIN", 9998, 60),  # buy 60 when limit is 50
        ]
        clipped = clip_orders("RESIN", orders, 0, 50)
        assert len(clipped) == 1
        assert clipped[0].quantity == 50, f"Expected clipped to 50, got {clipped[0].quantity}"

        # Already at limit
        clipped = clip_orders("RESIN", [Order("RESIN", 9998, 10)], 50, 50)
        assert len(clipped) == 0, "Should reject all buys when at limit"


# ===================================================================
# Market Making (EMA) — Tests 5-7
# ===================================================================

class TestMarketMakeEMA:

    def _config(self, **overrides):
        c = {
            "strategy": "market_make_ema",
            "position_limit": 50,
            "ema_alpha": 0.3,
            "spread": 2,
        }
        c.update(overrides)
        return c

    def test_ema_initializes_on_first_timestep(self):
        """5. EMA initializes correctly from first mid price."""
        od = make_order_depth({99: 10}, {101: 10})
        state = make_state(order_depths={"KELP": od}, trader_data="")
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        trader.strategy_market_make_ema("KELP", state, config, 0, 50)
        assert "KELP" in trader.state_data
        ema = trader.state_data["KELP"]["ema"]
        assert abs(ema - 100.0) < 0.01, f"First EMA should be mid=100, got {ema}"

    def test_ema_updates_and_persists(self):
        """6. EMA updates across timesteps via traderData."""
        # First timestep: mid = 100
        od1 = make_order_depth({99: 10}, {101: 10})
        state1 = make_state(order_depths={"KELP": od1}, trader_data="")
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        trader.strategy_market_make_ema("KELP", state1, config, 0, 50)
        ema1 = trader.state_data["KELP"]["ema"]

        # Second timestep: mid = 110, EMA should move toward 110
        od2 = make_order_depth({109: 10}, {111: 10})
        td = json.dumps(trader.state_data)
        state2 = make_state(order_depths={"KELP": od2}, trader_data=td)
        trader2 = Trader()
        trader2.state_data = json.loads(td)
        trader2.strategy_market_make_ema("KELP", state2, config, 0, 50)
        ema2 = trader2.state_data["KELP"]["ema"]
        # EMA(100 → 110, alpha=0.3) = 0.3*110 + 0.7*100 = 103
        assert abs(ema2 - 103.0) < 0.01, f"Expected EMA ~103, got {ema2}"

    def test_quotes_adjust_with_ema(self):
        """7. Quotes shift when EMA shifts."""
        od = make_order_depth({149: 10}, {151: 10})
        td = json.dumps({"KELP": {"ema": 100.0}})  # stale EMA far from current
        state = make_state(order_depths={"KELP": od}, trader_data=td)
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_market_make_ema("KELP", state, config, 0, 50)
        # EMA will update toward 150 (0.3*150 + 0.7*100 = 115)
        passive = [o for o in orders if abs(o.price - 150) > 5]
        # There should be quotes around ~115
        bids = [o for o in orders if o.quantity > 0]
        assert any(o.price < 120 for o in bids), "Bid should be near updated EMA ~115"


# ===================================================================
# Pairs Arb — Tests 8-11
# ===================================================================

class TestPairsArb:

    def _config(self, **overrides):
        c = {
            "strategy": "pairs_arb",
            "position_limit": 60,
            "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
            "z_entry": 2.0,
            "z_exit": 0.5,
            "spread_window": 50,
            "max_order_size": 10,
        }
        c.update(overrides)
        return c

    def _component_ods(self):
        """All components with mid=10, giving NAV=100."""
        return {
            "CROISSANTS": make_order_depth({9: 20}, {11: 20}),
            "JAMS": make_order_depth({9: 30}, {11: 30}),
            "DJEMBES": make_order_depth({9: 10}, {11: 10}),
        }

    def test_sells_basket_when_overpriced(self):
        """8. z > z_entry → sell basket."""
        basket_od = make_order_depth({102: 10}, {104: 10})  # mid=103, NAV=100, spread=3
        ods = {"PICNIC_BASKET1": basket_od, **self._component_ods()}
        td = json.dumps({"PICNIC_BASKET1": {"spread_history": [0.0] * 49}})
        state = make_state(order_depths=ods, trader_data=td)
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_pairs_arb("PICNIC_BASKET1", state, config, 0, 60)
        sells = [o for o in orders if o.quantity < 0]
        assert len(sells) > 0

    def test_buys_basket_when_underpriced(self):
        """9. z < -z_entry → buy basket."""
        basket_od = make_order_depth({96: 10}, {98: 10})  # mid=97, spread=-3
        ods = {"PICNIC_BASKET1": basket_od, **self._component_ods()}
        td = json.dumps({"PICNIC_BASKET1": {"spread_history": [0.0] * 49}})
        state = make_state(order_depths=ods, trader_data=td)
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_pairs_arb("PICNIC_BASKET1", state, config, 0, 60)
        buys = [o for o in orders if o.quantity > 0]
        assert len(buys) > 0

    def test_unwinds_position_near_zero_z(self):
        """10. |z| < z_exit with position → unwind."""
        basket_od = make_order_depth({100: 10}, {101: 10})  # mid=100.5, spread=0.5
        ods = {"PICNIC_BASKET1": basket_od, **self._component_ods()}
        td = json.dumps({"PICNIC_BASKET1": {"spread_history": [0.5] * 49}})
        state = make_state(order_depths=ods, trader_data=td, position={"PICNIC_BASKET1": 5})
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_pairs_arb("PICNIC_BASKET1", state, config, 5, 60)
        sells = [o for o in orders if o.quantity < 0]
        assert len(sells) > 0, "Should sell to unwind long position"

    def test_handles_missing_component(self):
        """11. Missing component order book → returns empty orders."""
        basket_od = make_order_depth({102: 10}, {104: 10})
        # Only CROISSANTS, missing JAMS and DJEMBES
        ods = {"PICNIC_BASKET1": basket_od, "CROISSANTS": make_order_depth({9: 20}, {11: 20})}
        state = make_state(order_depths=ods)
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        orders, _ = trader.strategy_pairs_arb("PICNIC_BASKET1", state, config, 0, 60)
        assert len(orders) == 0


# ===================================================================
# Informed Trader — Tests 12-15
# ===================================================================

class TestInformedTrader:

    def _config(self, **overrides):
        c = {
            "strategy": "informed_trader",
            "position_limit": 50,
            "tracked_traders": ["Olivia"],
            "flow_window": 10,
            "signal_threshold": 5,
            "base_spread": 2,
            "ema_alpha": 0.3,
        }
        c.update(overrides)
        return c

    def test_buys_on_positive_flow(self):
        """12. Tracked trader buying → aggressive buy orders."""
        od = make_order_depth({99: 10}, {101: 10})
        td = json.dumps({"SQUID": {"ema": 100.0, "flow_history": {"Olivia": [2] * 10}}})
        trades = [make_trade("SQUID", 101, 3, buyer="Olivia", seller="BOT")]
        state = make_state(
            order_depths={"SQUID": od}, market_trades={"SQUID": trades}, trader_data=td,
        )
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_informed_trader("SQUID", state, config, 0, 50)
        buys = [o for o in orders if o.quantity > 0]
        assert len(buys) > 0

    def test_sells_on_negative_flow(self):
        """13. Tracked trader selling → aggressive sell orders."""
        od = make_order_depth({99: 10}, {101: 10})
        td = json.dumps({"SQUID": {"ema": 100.0, "flow_history": {"Olivia": [-2] * 10}}})
        trades = [make_trade("SQUID", 99, 3, buyer="BOT", seller="Olivia")]
        state = make_state(
            order_depths={"SQUID": od}, market_trades={"SQUID": trades}, trader_data=td,
        )
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_informed_trader("SQUID", state, config, 0, 50)
        sells = [o for o in orders if o.quantity < 0]
        assert len(sells) > 0

    def test_passive_when_no_signal(self):
        """14. No signal → passive market making."""
        od = make_order_depth({99: 10}, {101: 10})
        td = json.dumps({"SQUID": {"ema": 100.0, "flow_history": {"Olivia": [0] * 10}}})
        state = make_state(
            order_depths={"SQUID": od}, market_trades={"SQUID": []}, trader_data=td,
        )
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_informed_trader("SQUID", state, config, 0, 50)
        buys = [o for o in orders if o.quantity > 0]
        sells = [o for o in orders if o.quantity < 0]
        assert len(buys) > 0 and len(sells) > 0, "Should place passive bid+ask"
        assert all(o.price <= 100 for o in buys)
        assert all(o.price >= 100 for o in sells)

    def test_flow_aggregates_across_timesteps(self):
        """15. Flow history accumulates across timesteps via traderData."""
        od = make_order_depth({99: 10}, {101: 10})
        # Start with 5 timesteps of +1 flow (not enough to trigger)
        td = json.dumps({"SQUID": {"ema": 100.0, "flow_history": {"Olivia": [1] * 5}}})
        # This timestep: Olivia buys 2 more → total = 5 + 2 = 7 > threshold 5
        trades = [make_trade("SQUID", 101, 2, buyer="Olivia", seller="BOT")]
        state = make_state(
            order_depths={"SQUID": od}, market_trades={"SQUID": trades}, trader_data=td,
        )
        config = self._config()
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_informed_trader("SQUID", state, config, 0, 50)
        buys = [o for o in orders if o.quantity > 0]
        assert len(buys) > 0, "Accumulated flow should exceed threshold"


# ===================================================================
# Cross Exchange — Tests 16-18
# ===================================================================

class TestCrossExchange:

    def _config(self, **overrides):
        c = {
            "strategy": "cross_exchange",
            "position_limit": 75,
            "conversion_product": "MACARONS",
            "storage_cost": 0.0,
            "spread_buffer": 1.0,
            "max_conversion": 10,
        }
        c.update(overrides)
        return c

    def _obs(self, bid=103, ask=108, transport=1, export_tariff=2, import_tariff=2):
        return Observation(
            conversionObservations={
                "MACARONS": ConversionObservation(
                    bidPrice=float(bid), askPrice=float(ask),
                    transportFees=float(transport),
                    exportTariff=float(export_tariff),
                    importTariff=float(import_tariff),
                )
            }
        )

    def test_buy_local_when_implied_bid_above_local_ask(self):
        """16. implied_bid > local_ask + buffer → buy + positive conversions."""
        # implied_bid = 103-2-1 = 100; local_ask = 95; 95 < 100-1=99 ✓
        od = make_order_depth({93: 10}, {95: 10})
        state = make_state(order_depths={"MACARONS": od}, observations=self._obs())
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        orders, conv = trader.strategy_cross_exchange("MACARONS", state, config, 0, 75)
        buys = [o for o in orders if o.quantity > 0]
        assert len(buys) > 0
        assert conv > 0

    def test_sell_local_when_implied_ask_below_local_bid(self):
        """17. local_bid > implied_ask + buffer → sell + negative conversions."""
        # implied_ask = 108+2+1 = 111; local_bid = 115; 115 > 111+1=112 ✓
        od = make_order_depth({115: 10}, {120: 10})
        state = make_state(order_depths={"MACARONS": od}, observations=self._obs())
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        orders, conv = trader.strategy_cross_exchange("MACARONS", state, config, 0, 75)
        sells = [o for o in orders if o.quantity < 0]
        assert len(sells) > 0
        assert conv < 0

    def test_no_arb_when_prices_in_range(self):
        """18. No arbitrage when local prices are between implied bid and ask."""
        # implied_bid = 100, implied_ask = 111
        # local: bid=104, ask=106 → both inside the range, no arb
        od = make_order_depth({104: 10}, {106: 10})
        state = make_state(order_depths={"MACARONS": od}, observations=self._obs())
        config = self._config()
        trader = Trader()
        trader.state_data = {}
        orders, conv = trader.strategy_cross_exchange("MACARONS", state, config, 0, 75)
        # Should have passive quotes only, no arb conversions
        assert conv == 0, f"No arb expected, got conversions={conv}"


# ===================================================================
# Circular Arb — Tests 19-20
# ===================================================================

class TestCircularArb:

    def test_generates_orders_when_profitable(self):
        """19. Profitable cycle → generates orders."""
        # Three products forming a cycle. Product of mids:
        # 1.05 * 1.0 * 1.0 = 1.05 → profit = 500 bps > 10
        od_a = make_order_depth({104: 10}, {106: 10})  # mid = 105 → ~1.05 rate
        od_b = make_order_depth({99: 10}, {101: 10})   # mid = 100 → 1.0 rate
        od_c = make_order_depth({99: 10}, {101: 10})   # mid = 100 → 1.0 rate
        ods = {"PROD_A": od_a, "PROD_B": od_b, "PROD_C": od_c}
        state = make_state(order_depths=ods)
        config = {
            "strategy": "circular_arb",
            "position_limit": 50,
            "cycle": ["PROD_A", "PROD_B", "PROD_C"],
            "rate_type": "mid",
            "min_profit_bps": 10,
            "max_order_size": 20,
            "cycle_role": "buy",
        }
        trader = Trader()
        trader.state_data = {}
        orders, _ = trader.strategy_circular_arb("PROD_A", state, config, 0, 50)
        assert len(orders) > 0, "Should generate orders for profitable cycle"

    def test_no_orders_when_not_profitable(self):
        """20. Unprofitable cycle → no orders."""
        # All mids = 100 → product = 1e6, but log_sum = 3*log(100) ≈ 13.8
        # exp(13.8) - 1 is huge... We need actual exchange RATES near 1.0.
        # Use rates: 1.001 * 0.999 * 1.0 ≈ 1.0 → ~0 bps profit
        # Encode as prices: 1001, 999, 1000 (mid of each)
        od_a = make_order_depth({1000: 10}, {1002: 10})  # mid=1001
        od_b = make_order_depth({998: 10}, {1000: 10})   # mid=999
        od_c = make_order_depth({999: 10}, {1001: 10})   # mid=1000
        # product = 1001*999*1000 = 999,999,000 → log_sum huge, not near 1.0
        # For circular arb with literal prices, the "product" check doesn't
        # make sense unless prices ARE rates (near 1.0). Let's use rate-like prices.
        od_a2 = make_order_depth({0: 10}, {2: 10})  # mid=1
        # Can't have price 0 in the book. Use small integers near 1:
        # Actually: the strategy uses mid_price which is (bb+ba)/2.
        # Let's just make all three have mid ~1.0 so product ≈ 1.0
        od_x = make_order_depth({1: 10}, {1: 10})  # mid=1
        od_y = make_order_depth({1: 10}, {1: 10})  # mid=1
        od_z = make_order_depth({1: 10}, {1: 10})  # mid=1
        ods = {"X": od_x, "Y": od_y, "Z": od_z}
        state = make_state(order_depths=ods)
        config = {
            "strategy": "circular_arb",
            "position_limit": 50,
            "cycle": ["X", "Y", "Z"],
            "rate_type": "mid",
            "min_profit_bps": 10,
            "max_order_size": 20,
            "cycle_role": "buy",
        }
        trader = Trader()
        trader.state_data = {}
        orders, _ = trader.strategy_circular_arb("X", state, config, 0, 50)
        assert len(orders) == 0, "Should not trade when cycle is not profitable"


# ===================================================================
# Options — Tests 21-25
# ===================================================================

class TestOptions:

    def test_bs_call_price_known_case(self):
        """21. BS call price matches known result: S=100,K=100,T=1,r=0.05,σ=0.2 ≈ 10.45."""
        price = bs_call_price(100, 100, 1.0, 0.05, 0.2)
        assert abs(price - 10.4506) < 0.05, f"Expected ~10.45, got {price:.4f}"

    def test_implied_vol_recovers_sigma(self):
        """22. implied_vol recovers sigma when given BS price as input."""
        sigma = 0.2
        price = bs_call_price(100, 100, 1.0, 0.05, sigma)
        recovered = implied_vol(price, 100, 100, 1.0, 0.05, "call")
        assert recovered is not None, "implied_vol should converge"
        assert abs(recovered - sigma) < 0.01, f"Expected ~0.2, got {recovered:.4f}"

    def test_delta_between_0_and_1(self):
        """23. Call delta is between 0 and 1, increases with S."""
        d_atm = bs_delta(100, 100, 1.0, 0.05, 0.2)
        d_itm = bs_delta(120, 100, 1.0, 0.05, 0.2)
        d_otm = bs_delta(80, 100, 1.0, 0.05, 0.2)
        assert 0 < d_atm < 1
        assert 0 < d_itm < 1
        assert 0 < d_otm < 1
        assert d_itm > d_atm > d_otm, (
            f"Delta should increase with S: ITM={d_itm:.3f}, ATM={d_atm:.3f}, OTM={d_otm:.3f}"
        )

    def test_strategy_buys_when_iv_low(self):
        """24. IV z < -z_entry → buy options."""
        # Set up: underlying mid=10000, option mid priced at low IV
        underlying_od = make_order_depth({9999: 50}, {10001: 50})  # mid=10000
        # Compute a low-IV call price: sigma=0.1, T=5/252
        low_iv_price = bs_call_price(10000, 10000, 5/252.0, 0.0, 0.1)
        opt_mid_int = int(round(low_iv_price))
        if opt_mid_int < 1:
            opt_mid_int = 1
        option_od = make_order_depth(
            {opt_mid_int - 1: 20}, {opt_mid_int + 1: 20}
        )
        # Pre-populate IV history with higher IVs so current IV is z << -1.5
        td = json.dumps({
            "VOUCHER_10000": {"iv_history": [0.3] * 19}
        })
        state = make_state(
            order_depths={"VOUCHER_10000": option_od, "VOLCANIC_ROCK": underlying_od},
            trader_data=td,
        )
        config = {
            "strategy": "options",
            "position_limit": 200,
            "underlying": "VOLCANIC_ROCK",
            "strike": 10000,
            "expiry_days": 5,
            "risk_free_rate": 0.0,
            "iv_window": 20,
            "iv_z_entry": 1.5,
            "iv_z_exit": 0.5,
            "delta_hedge": False,
            "max_order_size": 20,
        }
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_options("VOUCHER_10000", state, config, 0, 200)
        buys = [o for o in orders if o.quantity > 0]
        assert len(buys) > 0, f"Expected buy orders when IV is low, got {orders}"

    def test_strategy_sells_when_iv_high(self):
        """25. IV z > z_entry → sell options."""
        underlying_od = make_order_depth({9999: 50}, {10001: 50})
        # High-IV call price: sigma=0.5, T=5/252
        high_iv_price = bs_call_price(10000, 10000, 5/252.0, 0.0, 0.5)
        opt_mid_int = int(round(high_iv_price))
        option_od = make_order_depth(
            {opt_mid_int - 1: 20}, {opt_mid_int + 1: 20}
        )
        # Pre-populate IV history with lower IVs so current IV z >> 1.5
        td = json.dumps({
            "VOUCHER_10000": {"iv_history": [0.15] * 19}
        })
        state = make_state(
            order_depths={"VOUCHER_10000": option_od, "VOLCANIC_ROCK": underlying_od},
            trader_data=td,
        )
        config = {
            "strategy": "options",
            "position_limit": 200,
            "underlying": "VOLCANIC_ROCK",
            "strike": 10000,
            "expiry_days": 5,
            "risk_free_rate": 0.0,
            "iv_window": 20,
            "iv_z_entry": 1.5,
            "iv_z_exit": 0.5,
            "delta_hedge": False,
            "max_order_size": 20,
        }
        trader = Trader()
        trader.state_data = json.loads(td)
        orders, _ = trader.strategy_options("VOUCHER_10000", state, config, 0, 200)
        sells = [o for o in orders if o.quantity < 0]
        assert len(sells) > 0, f"Expected sell orders when IV is high, got {orders}"


# ===================================================================
# Infrastructure — Tests 26-28
# ===================================================================

class TestInfrastructure:

    def test_traderdata_round_trip(self):
        """26. traderData serialization round-trips correctly."""
        trader = Trader()
        trader.state_data = {
            "PRODUCT_A": {"ema": 100.5, "spread_history": [1.0, 2.0, 3.0]},
            "PRODUCT_B": {"flow_history": {"Olivia": [1, -1, 2]}},
        }
        s1 = trader._save_state()
        loaded = trader._load_state(s1)
        trader.state_data = loaded
        s2 = trader._save_state()
        assert json.loads(s1) == json.loads(s2), "Round-trip should produce identical JSON"

    def test_position_clipper_rejects_excess(self):
        """27. clip_orders clips and rejects orders exceeding limits."""
        # Multiple orders: first fills capacity, second rejected
        orders = [
            Order("X", 100, 30),
            Order("X", 101, 30),  # would push to 60, over limit 50
        ]
        clipped = clip_orders("X", orders, 0, 50)
        total = sum(o.quantity for o in clipped)
        assert total <= 50, f"Total qty {total} exceeds limit 50"
        assert total == 50, f"Should fill exactly to limit, got {total}"

        # Sell side
        sell_orders = [Order("X", 100, -40), Order("X", 99, -20)]
        clipped_sell = clip_orders("X", sell_orders, 0, 50)
        total_sell = sum(o.quantity for o in clipped_sell)
        assert total_sell >= -50, f"Total sell qty {total_sell} exceeds limit"

    def test_logger_produces_valid_json(self):
        """28. Logger flush produces valid JSON."""
        from trader import Logger
        test_logger = Logger()
        test_logger.print("test log message")
        od = make_order_depth({99: 10}, {101: 10})
        state = make_state(order_depths={"X": od})
        orders = {"X": [Order("X", 100, 5)]}
        # Capture the print output
        import io
        from unittest.mock import patch
        with patch("builtins.print") as mock_print:
            test_logger.flush(state, orders, 0, "{}")
        assert mock_print.called, "flush should call print"
        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        assert isinstance(parsed, list), "Output should be a JSON array"
