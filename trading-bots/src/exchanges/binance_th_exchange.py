"""Binance TH exchange connector."""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from loguru import logger

from .base_exchange import Balance, BaseExchange, OrderResult, Ticker


class BinanceThExchange(BaseExchange):
    """Binance TH exchange connector for cryptocurrency trading."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = "https://api.binance.th"
        self.session = None
        self.api_key = config.get("apiKey")
        self.secret_key = config.get("secret")
        self.test_mode = config.get("testMode", True)

    async def connect(self) -> bool:
        """Connect to Binance TH exchange."""
        try:
            self.session = aiohttp.ClientSession()

            # Test connection by getting server time
            server_time = await self._get_server_time()
            if server_time:
                logger.info(
                    f"Connected to Binance TH ({'test' if self.test_mode else 'live'} mode)"
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Binance TH: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Binance TH."""
        if self.session:
            await self.session.close()
            logger.info("Disconnected from Binance TH")

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for API requests."""
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _make_request(
        self, method: str, endpoint: str, params: dict = None, signed: bool = False
    ) -> dict:
        """Make HTTP request to Binance TH API."""
        url = f"{self.base_url}{endpoint}"
        headers = {}

        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        if params is None:
            params = {}

        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            params["signature"] = signature

        try:
            if method.upper() == "GET":
                async with self.session.get(
                    url, params=params, headers=headers
                ) as response:
                    data = await response.json()
            elif method.upper() == "POST":
                async with self.session.post(
                    url, data=params, headers=headers
                ) as response:
                    data = await response.json()
            elif method.upper() == "DELETE":
                async with self.session.delete(
                    url, params=params, headers=headers
                ) as response:
                    data = await response.json()
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Check for API errors
            if "code" in data and data["code"] != 0:
                raise Exception(
                    f"API Error {data['code']}: {data.get('msg', 'Unknown error')}"
                )

            return data
        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise

    async def _get_server_time(self) -> Optional[int]:
        """Get server time for connection test."""
        try:
            data = await self._make_request("GET", "/api/v1/time")
            return data.get("serverTime")
        except Exception as e:
            logger.error(f"Failed to get server time: {e}")
            return None

    async def get_balance(self, currency: str = None) -> Dict[str, Balance]:
        """Get account balance from Binance TH."""
        try:
            data = await self._make_request("GET", "/api/v1/accountV2", signed=True)
            balances = {}

            for balance_info in data.get("balances", []):
                curr = balance_info["asset"]

                if currency and curr != currency:
                    continue

                free_amount = float(balance_info["free"])
                locked_amount = float(balance_info["locked"])

                balances[curr] = Balance(
                    currency=curr,
                    free=free_amount,
                    used=locked_amount,
                    total=free_amount + locked_amount,
                )

            return balances
        except Exception as e:
            logger.error(f"Failed to get Binance TH balance: {e}")
            return {}

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current market ticker from Binance TH."""
        try:
            # Convert symbol format from BTC/USDT to BTCUSDT
            binance_symbol = symbol.replace("/", "")

            data = await self._make_request(
                "GET", "/api/v1/ticker/24hr", {"symbol": binance_symbol}
            )

            return Ticker(
                symbol=symbol,
                bid=float(data.get("bidPrice", 0)),
                ask=float(data.get("askPrice", 0)),
                last=float(data.get("lastPrice", 0)),
                volume=float(data.get("volume", 0)),
                timestamp=datetime.fromtimestamp(data.get("closeTime", 0) / 1000),
            )
        except Exception as e:
            logger.error(f"Failed to get Binance TH ticker for {symbol}: {e}")
            raise

    async def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float = None,
        order_type: str = "market",
    ) -> OrderResult:
        """Place a trading order on Binance TH."""
        try:
            # Convert symbol format from BTC/USDT to BTCUSDT
            binance_symbol = symbol.replace("/", "")

            params = {
                "symbol": binance_symbol,
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": amount,
            }

            if order_type.lower() == "limit":
                if price is None:
                    raise ValueError("Price is required for limit orders")
                params["price"] = price
                params["timeInForce"] = "GTC"

            data = await self._make_request(
                "POST", "/api/v1/order", params, signed=True
            )

            return OrderResult(
                order_id=str(data["orderId"]),
                symbol=symbol,
                side=side.lower(),
                amount=amount,
                price=float(data.get("price", price or 0)),
                status=self._convert_order_status(data["status"]),
                filled_amount=float(data.get("executedQty", 0)),
                fees=sum(
                    float(fill.get("commission", 0)) for fill in data.get("fills", [])
                ),
                timestamp=datetime.fromtimestamp(data.get("transactTime", 0) / 1000),
            )
        except Exception as e:
            logger.error(f"Failed to place order on Binance TH: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order on Binance TH."""
        try:
            params = {"symbol": symbol, "orderId": order_id}

            await self._make_request("DELETE", "/api/v1/order", params, signed=True)
            logger.info(f"Successfully cancelled order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Get status of an existing order from Binance TH."""
        try:
            params = {"symbol": symbol, "orderId": order_id}

            data = await self._make_request("GET", "/api/v1/order", params, signed=True)

            return OrderResult(
                order_id=str(data["orderId"]),
                symbol=data["symbol"],
                side=data["side"].lower(),
                amount=float(data["origQty"]),
                price=float(data["price"]),
                status=self._convert_order_status(data["status"]),
                filled_amount=float(data["executedQty"]),
                fees=0.0,  # Would need separate API call to get fees
                timestamp=datetime.fromtimestamp(data.get("time", 0) / 1000),
            )
        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            raise

    async def get_open_orders(self, symbol: str = None) -> List[OrderResult]:
        """Get all open orders from Binance TH."""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol

            data = await self._make_request(
                "GET", "/api/v1/openOrders", params, signed=True
            )
            orders = []

            for order_data in data:
                orders.append(
                    OrderResult(
                        order_id=str(order_data["orderId"]),
                        symbol=order_data["symbol"],
                        side=order_data["side"].lower(),
                        amount=float(order_data["origQty"]),
                        price=float(order_data["price"]),
                        status=self._convert_order_status(order_data["status"]),
                        filled_amount=float(order_data["executedQty"]),
                        fees=0.0,
                        timestamp=datetime.fromtimestamp(
                            order_data.get("time", 0) / 1000
                        ),
                    )
                )

            return orders
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def get_order_history(
        self, symbol: str = None, limit: int = 100
    ) -> List[OrderResult]:
        """Get order history from Binance TH."""
        try:
            params = {"limit": min(limit, 1000)}
            if symbol:
                params["symbol"] = symbol

            data = await self._make_request(
                "GET", "/api/v1/allOrders", params, signed=True
            )
            orders = []

            for order_data in data:
                orders.append(
                    OrderResult(
                        order_id=str(order_data["orderId"]),
                        symbol=order_data["symbol"],
                        side=order_data["side"].lower(),
                        amount=float(order_data["origQty"]),
                        price=float(order_data["price"]),
                        status=self._convert_order_status(order_data["status"]),
                        filled_amount=float(order_data["executedQty"]),
                        fees=0.0,
                        timestamp=datetime.fromtimestamp(
                            order_data.get("time", 0) / 1000
                        ),
                    )
                )

            return orders
        except Exception as e:
            logger.error(f"Failed to get order history: {e}")
            return []

    def get_supported_symbols(self) -> List[str]:
        """Get list of supported trading symbols."""
        # This would typically be fetched from the exchange info endpoint
        # For now, return common symbols available on Binance TH
        return [
            "BTCTHB",
            "ETHTHB",
            "ADATHB",
            "DOTTHB",
            "XRPTHB",
            "LTCTHB",
            "LINKTHB",
            "BCHTHB",
            "XLMTHB",
            "EOSTHB",
            "BTCUSDT",
            "ETHUSDT",
            "ADAUSDT",
            "DOTUSDT",
            "XRPUSDT",
        ]

    def get_market_type(self) -> str:
        """Get market type."""
        return "crypto"

    def _convert_order_status(self, binance_status: str) -> str:
        """Convert Binance TH order status to standard format."""
        status_map = {
            "NEW": "pending",
            "PARTIALLY_FILLED": "partial",
            "FILLED": "filled",
            "CANCELED": "cancelled",
            "REJECTED": "rejected",
            "EXPIRED": "expired",
        }
        return status_map.get(binance_status, "unknown")

    async def get_exchange_info(self) -> dict:
        """Get exchange information including trading symbols and filters."""
        try:
            data = await self._make_request("GET", "/api/v1/exchangeInfo")
            return data
        except Exception as e:
            logger.error(f"Failed to get exchange info: {e}")
            return {}

    async def get_klines(
        self, symbol: str, interval: str = "1m", limit: int = 100
    ) -> List[List]:
        """Get kline/candlestick data."""
        try:
            params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}

            data = await self._make_request("GET", "/api/v1/klines", params)
            return data
        except Exception as e:
            logger.error(f"Failed to get klines: {e}")
            return []
