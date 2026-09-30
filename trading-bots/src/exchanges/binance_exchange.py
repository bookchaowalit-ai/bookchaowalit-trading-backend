"""Binance exchange connector."""

import math
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt
from loguru import logger

from .base_exchange import (
    Balance,
    BaseExchange,
    OrderResult,
    Ticker,
    fee_to_quote,
    ohlcv_frame,
    split_symbol,
    utc_from_ms,
)


def _finite(value: Any) -> Optional[float]:
    """``value`` as a float when it is a finite number, else ``None``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _order_fee(order: Dict[str, Any], symbol: str = "", price: float = 0.0) -> float:
    """Total fee cost of a ccxt order, in ``symbol``'s quote currency.

    ccxt always includes the ``fee`` key but sets it to ``None`` when the
    exchange reported no fee (common for Binance market orders), so
    ``order.get("fee", {}).get(...)`` raised ``AttributeError`` *after* the
    order had been placed. Multi-asset fills report a ``fees`` list instead.
    Binance charges buy commissions in the base asset by default, so each
    fee is converted with its own ``currency`` (base -> ``cost * price``).
    Without a ``symbol`` the raw costs are summed (legacy behavior).
    """
    def convert(item: Dict[str, Any]) -> float:
        cost = _finite(item.get("cost"))
        if cost is None:
            return 0.0
        if not symbol:
            return cost
        return fee_to_quote(cost, item.get("currency"), symbol, price)

    fee = order.get("fee")
    if isinstance(fee, dict) and _finite(fee.get("cost")) is not None:
        return convert(fee)
    total = 0.0
    for item in order.get("fees") or []:
        if isinstance(item, dict):
            total += convert(item)
    return total


def _order_result(
    order: Dict[str, Any],
    symbol: str,
    side: str,
    amount: Optional[float] = None,
    fallback_price: Optional[float] = None,
    default_status: str = "unknown",
) -> OrderResult:
    """Map a ccxt order onto ``OrderResult`` without trusting nullable fields.

    ccxt sets ``price`` to ``None`` (or 0) on market orders and puts the
    execution price in ``average``; ``filled``/``amount`` may be ``None`` too.
    The execution price prefers ``average``, then ``price``, then the caller's
    reference price.
    """
    price = next(
        (
            value
            for value in (_finite(order.get("average")), _finite(order.get("price")), _finite(fallback_price))
            if value is not None and value > 0
        ),
        0.0,
    )
    requested = _finite(order.get("amount"))
    return OrderResult(
        order_id=order["id"],
        symbol=order.get("symbol") or symbol,
        side=order.get("side") or side,
        amount=amount if amount is not None else (requested or 0.0),
        price=price,
        status=order.get("status") or default_status,
        filled_amount=_finite(order.get("filled")) or 0.0,
        fees=_order_fee(order, order.get("symbol") or symbol, price),
        fee_currency=split_symbol(order.get("symbol") or symbol)[1],
        timestamp=utc_from_ms(order.get("timestamp") or 0),
    )


class BinanceExchange(BaseExchange):
    """Binance exchange connector for cryptocurrency trading."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.exchange = None

    async def connect(self) -> bool:
        """Connect to Binance exchange."""
        try:
            self.exchange = ccxt.binance(
                {
                    "apiKey": self.config.get("apiKey"),
                    "secret": self.config.get("secret"),
                    "sandbox": self.config.get("sandbox", True),
                    "enableRateLimit": True,
                }
            )

            # Test connection
            await self.exchange.load_markets()
            logger.info(
                f"Connected to Binance ({'sandbox' if self.config.get('sandbox') else 'live'})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Binance."""
        if self.exchange:
            await self.exchange.close()
            logger.info("Disconnected from Binance")

    async def get_balance(self, currency: str = None) -> Dict[str, Balance]:
        """Get account balance from Binance."""
        try:
            balance_data = await self.exchange.fetch_balance()
            balances = {}

            for curr, data in balance_data.items():
                if curr in ["free", "used", "total"]:
                    continue

                if currency and curr != currency:
                    continue

                balances[curr] = Balance(
                    currency=curr,
                    free=data.get("free", 0.0),
                    used=data.get("used", 0.0),
                    total=data.get("total", 0.0),
                )

            return balances
        except Exception as e:
            logger.error(f"Failed to get Binance balance: {e}")
            return {}

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current market ticker from Binance."""
        try:
            ticker_data = await self.exchange.fetch_ticker(symbol)
            return Ticker(
                symbol=symbol,
                bid=ticker_data.get("bid", 0.0),
                ask=ticker_data.get("ask", 0.0),
                last=ticker_data.get("last", 0.0),
                volume=ticker_data.get("baseVolume", 0.0),
                timestamp=utc_from_ms(ticker_data.get("timestamp", 0)),
            )
        except Exception as e:
            logger.error(f"Failed to get Binance ticker for {symbol}: {e}")
            raise

    async def get_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200):
        """Recent OHLCV bars via ccxt ``fetch_ohlcv`` (public endpoint)."""
        rows = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return ohlcv_frame(rows)

    async def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float = None,
        order_type: str = "market",
    ) -> OrderResult:
        """Place a trading order on Binance."""
        try:
            if order_type == "market":
                order = await self.exchange.create_market_order(symbol, side, amount)
            else:
                order = await self.exchange.create_limit_order(
                    symbol, side, amount, price
                )

            return _order_result(order, symbol, side, amount, price, default_status="pending")
        except Exception as e:
            logger.error(f"Failed to place Binance order: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order on Binance."""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"Cancelled Binance order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel Binance order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Get status of an existing order on Binance."""
        try:
            order = await self.exchange.fetch_order(order_id, symbol)
            return _order_result(order, symbol, order.get("side"))
        except Exception as e:
            logger.error(f"Failed to get Binance order status: {e}")
            raise

    async def get_open_orders(self, symbol: str = None) -> List[OrderResult]:
        """Get all open orders from Binance."""
        try:
            orders = await self.exchange.fetch_open_orders(symbol)
            return [
                _order_result(order, order.get("symbol"), order.get("side"), default_status="open")
                for order in orders
            ]
        except Exception as e:
            logger.error(f"Failed to get Binance open orders: {e}")
            return []

    async def get_order_history(
        self, symbol: str = None, limit: int = 100
    ) -> List[OrderResult]:
        """Get order history from Binance."""
        try:
            orders = await self.exchange.fetch_orders(symbol, limit=limit)
            return [
                _order_result(order, order.get("symbol"), order.get("side"), default_status="unknown")
                for order in orders
            ]
        except Exception as e:
            logger.error(f"Failed to get Binance order history: {e}")
            return []

    def get_supported_symbols(self) -> List[str]:
        """Get list of supported trading symbols on Binance."""
        if not self.exchange or not self.exchange.markets:
            return []
        return list(self.exchange.markets.keys())

    def get_market_type(self) -> str:
        """Get market type for Binance."""
        return "crypto"
