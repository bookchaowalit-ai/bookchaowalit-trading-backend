"""Base exchange interface for trading bots."""

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional, Any, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import math

import pandas as pd
from loguru import logger


def utc_from_ms(ms: Any) -> datetime:
    """Exchange epoch milliseconds as a naive UTC ``datetime``.

    Naive UTC is the convention of ``datetime.utcnow()`` used by the paper
    exchange and the database layer. ``fromtimestamp()`` without a
    tz returns host-local time, so live orders were stamped hours away from
    paper orders and ``created_at`` on any non-UTC host.
    """
    return datetime.fromtimestamp((ms or 0) / 1000, tz=timezone.utc).replace(tzinfo=None)


def split_symbol(symbol: str) -> tuple:
    """``(base, quote)`` for ``BTC/USDT``, Bitkub ``THB_BTC`` or ``BTCUSDT``."""
    if "/" in symbol:
        base, quote = symbol.split("/", 1)
        return base, quote
    if "_" in symbol:  # Bitkub style THB_BTC
        quote, base = symbol.split("_", 1)
        return base, quote
    for quote in ("USDT", "THB", "USD", "BUSD"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, "USD"


def fee_to_quote(cost: Any, currency: Optional[str], symbol: str, price: float) -> float:
    """One fee amount expressed in ``symbol``'s quote currency.

    A fee charged in the base asset (e.g. Binance deducting the commission
    from the bought coins) is worth ``cost * price`` quote. A fee in a third
    asset (e.g. BNB) cannot be priced here; it is ignored with a warning
    rather than being added as if it were quote currency.
    """
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(cost) or cost == 0:
        return 0.0
    base, quote = split_symbol(symbol)
    cur = (currency or "").upper()
    if not cur or cur == quote.upper():
        return cost
    if cur == base.upper():
        return cost * price if math.isfinite(price) and price > 0 else 0.0
    logger.warning(f"Fee of {cost} {currency} on {symbol} is not in base/quote; excluded from PnL")
    return 0.0


def order_fee_in_quote(result: "OrderResult", symbol: Optional[str] = None) -> float:
    """``result.fees`` converted to the quote currency of the traded symbol."""
    return fee_to_quote(result.fees or 0.0, result.fee_currency, symbol or result.symbol, result.price)


def utc_now() -> datetime:
    """Current time as naive UTC (same convention as :func:`utc_from_ms`)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class OrderResult:
    """Result of a trading order."""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    price: float
    status: str  # 'filled', 'partial', 'cancelled', 'pending'
    filled_amount: float = 0.0
    fees: float = 0.0
    timestamp: datetime = None
    # Currency ``fees`` is denominated in. ``None`` means the quote currency
    # (the convention of every connector that does not report it).
    fee_currency: Optional[str] = None


@dataclass
class Balance:
    """Account balance information."""
    currency: str
    free: float
    used: float
    total: float


@dataclass
class Ticker:
    """Market ticker information."""
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: datetime


class BaseExchange(ABC):
    """Abstract base class for exchange connectors."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__.lower().replace('exchange', '')
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the exchange."""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from the exchange."""
        pass
    
    @abstractmethod
    async def get_balance(self, currency: str = None) -> Dict[str, Balance]:
        """Get account balance."""
        pass
    
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current market ticker."""
        pass
    
    @abstractmethod
    async def place_order(
        self, 
        symbol: str, 
        side: str, 
        amount: float, 
        price: float = None,
        order_type: str = "market"
    ) -> OrderResult:
        """Place a trading order."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Get status of an existing order."""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: str = None) -> List[OrderResult]:
        """Get all open orders."""
        pass
    
    @abstractmethod
    async def get_order_history(self, symbol: str = None, limit: int = 100) -> List[OrderResult]:
        """Get order history."""
        pass
    
    @abstractmethod
    def get_supported_symbols(self) -> List[str]:
        """Get list of supported trading symbols."""
        pass
    
    @abstractmethod
    def get_market_type(self) -> str:
        """Get market type (crypto, stock, forex)."""
        pass

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1m", limit: int = 200
    ) -> Optional[pd.DataFrame]:
        """Return recent OHLCV bars, or ``None`` when the connector has none.

        Connectors that expose klines override this and return the frame built
        by :func:`ohlcv_frame`. The default keeps older connectors working.
        """
        return None


OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

_TIMEFRAME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def timeframe_seconds(timeframe: str) -> int:
    """Convert a ccxt/Binance timeframe such as ``1m`` or ``4h`` to seconds."""
    tf = (timeframe or "").strip()
    unit = _TIMEFRAME_UNITS.get(tf[-1:].lower()) if tf else None
    if unit is None or not tf[:-1].isdigit() or int(tf[:-1]) <= 0:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")
    return int(tf[:-1]) * unit


def ohlcv_frame(rows: Iterable[Sequence[Any]]) -> pd.DataFrame:
    """Build a clean OHLCV frame from ``[open_time_ms, o, h, l, c, v, ...]`` rows.

    Accepts ccxt ``fetch_ohlcv`` rows and raw Binance klines (string prices,
    extra trailing fields). Rows with missing or non-positive prices, or with
    a high below the low, are dropped; bars are sorted by open time and
    de-duplicated (the last copy wins). ``timestamp`` is the bar open time as
    a naive UTC datetime.
    """
    records = []
    for row in rows or []:
        try:
            ts = int(row[0])
            o, h, low, c = (float(row[i]) for i in range(1, 5))
            v = float(row[5]) if len(row) > 5 and row[5] is not None else 0.0
        except (TypeError, ValueError, IndexError):
            continue
        if min(o, h, low, c) <= 0 or h < low or v < 0:
            continue
        records.append((ts, o, h, low, c, v))

    df = pd.DataFrame.from_records(records, columns=OHLCV_COLUMNS)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp", keep="last").sort_values("timestamp")
    return df.reset_index(drop=True)


def closed_bars(df: pd.DataFrame, timeframe: str, now: datetime) -> pd.DataFrame:
    """Drop bars that are still forming at ``now`` (naive UTC).

    Exchanges return the current, still-changing candle last; indicators must
    only see bars whose close time has passed.
    """
    if df.empty:
        return df
    width = pd.Timedelta(seconds=timeframe_seconds(timeframe))
    return df[df["timestamp"] + width <= pd.Timestamp(now)].reset_index(drop=True)
