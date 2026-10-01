"""Paper-trading wrapper that never sends orders to a real exchange.

Only Binance (via ccxt sandbox) honoured the old ``TRADING_MODE=paper`` flag;
Binance TH, Bitkub and InnovestX connectors sent signed orders regardless.
``PaperExchange`` wraps any connector: public market data (tickers) still
comes from the wrapped exchange, while balances and orders are simulated
in memory.
"""

import math
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from .base_exchange import Balance, BaseExchange, OrderResult, Ticker, split_symbol

DEFAULT_PAPER_FEE_RATE = 0.001  # 0.1% taker fee


def _positive_finite(value) -> bool:
    try:
        return math.isfinite(value) and value > 0
    except TypeError:
        return False


class PaperOrderError(ValueError):
    """Raised when a simulated order would be impossible on a real account."""


class PaperExchange(BaseExchange):
    """Simulated spot account on top of a real exchange's market data."""

    def __init__(
        self,
        inner: BaseExchange,
        starting_balances: Optional[Dict[str, float]] = None,
        fee_rate: float = DEFAULT_PAPER_FEE_RATE,
    ):
        super().__init__(getattr(inner, "config", {}) or {})
        self.inner = inner
        self.name = f"paper_{getattr(inner, 'name', 'exchange')}"
        self.fee_rate = fee_rate
        self.balances: Dict[str, float] = dict(starting_balances or {"USDT": 10_000.0, "THB": 300_000.0})
        self.orders: List[OrderResult] = []

    async def connect(self) -> bool:
        # Public endpoints only; a failed private "connect" must not block paper runs.
        try:
            await self.inner.connect()
        except Exception as e:  # pragma: no cover - depends on network
            logger.warning(f"Paper mode: market-data connect failed: {e}")
        return True

    async def disconnect(self):
        await self.inner.disconnect()

    async def get_ticker(self, symbol: str) -> Ticker:
        return await self.inner.get_ticker(symbol)

    async def get_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200):
        # Public market data comes from the wrapped exchange.
        return await self.inner.get_ohlcv(symbol, timeframe=timeframe, limit=limit)

    async def get_balance(self, currency: str = None) -> Dict[str, Balance]:
        items = self.balances.items()
        if currency:
            items = [(currency, self.balances.get(currency, 0.0))]
        return {cur: Balance(currency=cur, free=amt, used=0.0, total=amt) for cur, amt in items}

    @staticmethod
    def _split_symbol(symbol: str) -> tuple:
        return split_symbol(symbol)

    async def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float = None,
        order_type: str = "market",
    ) -> OrderResult:
        side = side.lower()
        if side not in ("buy", "sell"):
            raise PaperOrderError(f"unsupported side {side!r}")
        # NaN passes `not x` and `x <= 0`; one NaN fill poisons every balance.
        if not _positive_finite(amount):
            raise PaperOrderError("order amount must be a positive finite number")

        if order_type == "market" or not price:
            fill_price = (await self.get_ticker(symbol)).last
        else:
            fill_price = price
        if not _positive_finite(fill_price):
            raise PaperOrderError(f"no valid price for {symbol}")

        base, quote = self._split_symbol(symbol)
        notional = amount * fill_price
        fee = notional * self.fee_rate

        if side == "buy":
            if self.balances.get(quote, 0.0) < notional + fee:
                raise PaperOrderError(f"insufficient {quote} for paper buy of {amount} {base}")
            self.balances[quote] = self.balances.get(quote, 0.0) - notional - fee
            self.balances[base] = self.balances.get(base, 0.0) + amount
        else:
            if self.balances.get(base, 0.0) + 1e-12 < amount:
                raise PaperOrderError(f"insufficient {base} for paper sell of {amount}")
            self.balances[base] = self.balances.get(base, 0.0) - amount
            self.balances[quote] = self.balances.get(quote, 0.0) + notional - fee

        result = OrderResult(
            order_id=f"paper-{uuid.uuid4()}",
            symbol=symbol,
            side=side,
            amount=amount,
            price=fill_price,
            status="filled",
            filled_amount=amount,
            fees=fee,
            fee_currency=quote,
            timestamp=datetime.utcnow(),
        )
        self.orders.append(result)
        logger.info(f"[PAPER] {side} {amount} {symbol} @ {fill_price} (fee {fee:.6f})")
        return result

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        return False  # paper orders fill immediately; nothing to cancel

    async def get_order_status(self, order_id: str, symbol: str) -> OrderResult:
        for order in self.orders:
            if order.order_id == order_id:
                return order
        raise PaperOrderError(f"unknown paper order {order_id}")

    async def get_open_orders(self, symbol: str = None) -> List[OrderResult]:
        return []

    async def get_order_history(self, symbol: str = None, limit: int = 100) -> List[OrderResult]:
        orders = [o for o in self.orders if symbol is None or o.symbol == symbol]
        return orders[-limit:]

    def get_supported_symbols(self) -> List[str]:
        return self.inner.get_supported_symbols()

    def get_market_type(self) -> str:
        return self.inner.get_market_type()
