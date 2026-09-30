"""Base exchange interface for trading bots."""

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional, Any, Sequence
from dataclasses import dataclass
from datetime import datetime

import pandas as pd


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
