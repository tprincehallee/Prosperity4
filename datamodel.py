"""
IMC Prosperity datamodel stub for local development.

This mirrors the competition-provided datamodel.py so that code can be
developed, tested, and type-checked locally. During submission, the
competition environment provides its own datamodel module — this file
is NOT submitted.

Based on Prosperity 3 datamodel; Prosperity 4 may add fields.
Update this file when the P4 Wiki is available.
"""

from typing import Dict, List, Any
import json

Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = float


class Listing:
    """Represents a tradeable product listing."""

    def __init__(self, symbol: Symbol, product: Product, denomination: Symbol):
        self.symbol = symbol
        self.product = product
        self.denomination = denomination


class Order:
    """
    An order to buy or sell a product.

    Attributes:
        symbol: Product symbol (e.g., "RAINFOREST_RESIN").
        price: Integer price level.
        quantity: Positive for buy, negative for sell.
    """

    def __init__(self, symbol: Symbol, price: int, quantity: int) -> None:
        self.symbol = symbol
        self.price = price
        self.quantity = quantity

    def __str__(self) -> str:
        return f"({self.symbol}, {self.price}, {self.quantity})"

    def __repr__(self) -> str:
        return f"Order({self.symbol}, {self.price}, {self.quantity})"


class OrderDepth:
    """
    Snapshot of the order book for a single product.

    Attributes:
        buy_orders: dict mapping price -> positive quantity (bids).
        sell_orders: dict mapping price -> negative quantity (asks).
    """

    def __init__(self):
        self.buy_orders: Dict[int, int] = {}
        self.sell_orders: Dict[int, int] = {}

    def __str__(self) -> str:
        return f"OrderDepth(buys={self.buy_orders}, sells={self.sell_orders})"


class Trade:
    """
    A completed trade between two market participants.

    Attributes:
        symbol: Product symbol.
        price: Execution price.
        quantity: Traded quantity (always positive).
        buyer: Trader ID of the buyer (e.g., "Olivia", "YOU").
        seller: Trader ID of the seller.
        timestamp: Simulation timestamp of the trade.
    """

    def __init__(
        self,
        symbol: Symbol,
        price: int,
        quantity: int,
        buyer: UserId = "",
        seller: UserId = "",
        timestamp: Time = 0,
    ) -> None:
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp

    def __str__(self) -> str:
        return (
            f"Trade({self.symbol}, price={self.price}, qty={self.quantity}, "
            f"buyer={self.buyer}, seller={self.seller}, t={self.timestamp})"
        )

    def __repr__(self) -> str:
        return self.__str__()


class ConversionObservation:
    """
    Foreign exchange observation for cross-exchange products (e.g., Macarons).

    Use to compute implied local prices:
        implied_bid = bidPrice - exportTariff - transportFees
        implied_ask = askPrice + importTariff + transportFees
    """

    def __init__(
        self,
        bidPrice: float,
        askPrice: float,
        transportFees: float,
        exportTariff: float,
        importTariff: float,
        sugarPrice: float = 0.0,
        sunlightIndex: float = 0.0,
    ) -> None:
        self.bidPrice = bidPrice
        self.askPrice = askPrice
        self.transportFees = transportFees
        self.exportTariff = exportTariff
        self.importTariff = importTariff
        self.sugarPrice = sugarPrice
        self.sunlightIndex = sunlightIndex


class Observation:
    """
    External observations available at each timestep.

    Attributes:
        plainValueObservations: dict of signal_name -> float value.
        conversionObservations: dict of product -> ConversionObservation.
    """

    def __init__(
        self,
        plainValueObservations: Dict[str, ObservationValue] = None,
        conversionObservations: Dict[str, ConversionObservation] = None,
    ) -> None:
        self.plainValueObservations = plainValueObservations or {}
        self.conversionObservations = conversionObservations or {}


class TradingState:
    """
    Complete market state passed to Trader.run() each timestep.

    Attributes:
        timestamp: Current simulation time (increments by 100 each step).
        traderData: JSON string you returned last timestep ("" on first call).
        listings: symbol -> Listing for all tradeable products.
        order_depths: symbol -> OrderDepth (current order book snapshot).
        own_trades: symbol -> list of your fills since last timestep.
        market_trades: symbol -> list of other participants' trades.
        position: symbol -> your current position (0 if not yet traded).
        observations: Observation object with external signals.
    """

    def __init__(
        self,
        traderData: str,
        timestamp: Time,
        listings: Dict[Symbol, Listing],
        order_depths: Dict[Symbol, OrderDepth],
        own_trades: Dict[Symbol, List[Trade]],
        market_trades: Dict[Symbol, List[Trade]],
        position: Dict[Product, Position],
        observations: Observation,
    ) -> None:
        self.traderData = traderData
        self.timestamp = timestamp
        self.listings = listings
        self.order_depths = order_depths
        self.own_trades = own_trades
        self.market_trades = market_trades
        self.position = position
        self.observations = observations

    def toJSON(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True)


class ProsperityEncoder(json.JSONEncoder):
    """JSON encoder that handles datamodel objects."""

    def default(self, o: Any) -> Any:
        return o.__dict__
