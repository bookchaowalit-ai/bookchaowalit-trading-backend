"""Bitkub exchange connector for trading bots."""

import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from .base_exchange import Balance, BaseExchange, OrderResult, Ticker


# Bitkub quotes every market in THB with 2 decimals; base assets use up to 8.
THB_QUANT = Decimal("0.01")
BASE_QUANT = Decimal("0.00000001")
# Bitkub rejects orders below 10 THB of notional.
BITKUB_MIN_ORDER_THB = Decimal("10")


def bitkub_order_payload(
    symbol: str,
    side: str,
    base_amount: float,
    reference_price: float,
    order_type: str = "market",
    limit_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a Bitkub place-bid / place-ask body from a *base-asset* quantity.

    Every strategy and the ``BaseExchange.place_order`` contract speak in base
    units (e.g. 0.001 BTC). Bitkub does not: for ``place-bid`` (buy) ``amt`` is
    the THB to spend, for ``place-ask`` (sell) ``amt`` is the base quantity.
    Sending a base quantity as a bid ``amt`` would try to buy 0.001 THB of BTC;
    sending THB as an ask ``amt`` would try to sell thousands of coins.

    Buys convert with ``base_amount * price`` where price is the limit rate for
    limit orders, else ``reference_price`` (the current ask). Amounts round
    *down* so an order never spends or sells more than requested.
    """
    side_l = side.lower()
    if side_l not in ("buy", "sell"):
        raise ValueError(f"unsupported side {side!r}")
    if order_type not in ("market", "limit"):
        raise ValueError(f"unsupported order type {order_type!r}")
    base = Decimal(str(base_amount))
    if base <= 0:
        raise ValueError("order amount must be a positive base-asset quantity")
    if order_type == "limit":
        if limit_price is None or limit_price <= 0:
            raise ValueError("limit orders need a positive price")
        rate = Decimal(str(limit_price))
    else:
        if reference_price is None or reference_price <= 0:
            raise ValueError("market orders need a positive reference price")
        rate = Decimal(str(reference_price))

    notional_thb = (base * rate).quantize(THB_QUANT, rounding=ROUND_DOWN)
    if notional_thb < BITKUB_MIN_ORDER_THB:
        raise ValueError(
            f"order notional {notional_thb} THB is below the Bitkub minimum of {BITKUB_MIN_ORDER_THB} THB"
        )

    if side_l == "buy":
        body: Dict[str, Any] = {"sym": symbol, "amt": float(notional_thb), "typ": order_type}
    else:
        quantity = base.quantize(BASE_QUANT, rounding=ROUND_DOWN)
        body = {"sym": symbol, "amt": float(quantity), "typ": order_type}
    body["rat"] = float(rate) if order_type == "limit" else 0
    return body


class BitkubExchange(BaseExchange):
    """Bitkub exchange connector for crypto trading."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("apiKey")
        self.api_secret = config.get("secret")
        self.base_url = config.get("baseUrl", "https://api.bitkub.com")
        self.session: Optional[aiohttp.ClientSession] = None

        # Bitkub specific settings
        self.supported_symbols = [
            "THB_BTC",
            "THB_ETH",
            "THB_ADA",
            "THB_XRP",
            "THB_LTC",
            "THB_BCH",
            "THB_EOS",
            "THB_BSV",
            "THB_USDT",
            "THB_LINK",
            "THB_OMG",
            "THB_DOT",
            "THB_UNI",
            "THB_USDC",
            "THB_DOGE",
            "THB_BNB",
            "THB_MATIC",
            "THB_SOL",
            "THB_AVAX",
            "THB_NEAR",
        ]

    def _generate_signature(
        self, timestamp: str, method: str, request_path: str, body: str = ""
    ) -> str:
        """Generate HMAC-SHA256 signature for Bitkub API."""
        payload = timestamp + method.upper() + request_path + (body or "")
        return hmac.new(
            self.api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _get_headers(
        self, method: str, request_path: str, body: str = ""
    ) -> Dict[str, str]:
        """Get authentication headers for Bitkub API."""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, request_path, body)

        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-BTK-APIKEY": self.api_key,
            "X-BTK-TIMESTAMP": timestamp,
            "X-BTK-SIGN": signature,
        }

    async def _make_request(
        self, method: str, endpoint: str, data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Bitkub API."""
        if not self.session:
            raise Exception("Not connected to exchange")

        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data) if data else ""
        headers = self._get_headers(method, endpoint, body)

        try:
            async with self.session.request(
                method=method, url=url, headers=headers, data=body if body else None
            ) as response:
                result = await response.json()

                # Check for API errors
                if result.get("error", 0) != 0:
                    error_msg = f"Bitkub API error {result.get('error')}: {result.get('message', 'Unknown error')}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

                return result

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error during Bitkub API request: {e}")
            raise
        except Exception as e:
            logger.error(f"Error making Bitkub API request: {e}")
            raise

    async def _make_public_request(self, endpoint: str) -> Dict[str, Any]:
        """Make public request (no authentication required)."""
        if not self.session:
            raise Exception("Not connected to exchange")

        url = f"{self.base_url}{endpoint}"
        headers = {"Accept": "application/json"}

        try:
            async with self.session.get(url, headers=headers) as response:
                result = await response.json()

                # Check for API errors
                if result.get("error", 0) != 0:
                    error_msg = f"Bitkub API error {result.get('error')}: {result.get('message', 'Unknown error')}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

                return result

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error during Bitkub public API request: {e}")
            raise
        except Exception as e:
            logger.error(f"Error making Bitkub public API request: {e}")
            raise

    async def connect(self) -> bool:
        """Connect to Bitkub exchange."""
        try:
            if not self.api_key or not self.api_secret:
                logger.error("Bitkub API credentials not provided")
                return False

            self.session = aiohttp.ClientSession()

            # Test connection with server time
            server_time = await self._make_public_request("/api/servertime")
            logger.info(
                f"Connected to Bitkub exchange. Server time: {server_time.get('result')}"
            )

            # Test authentication with wallet endpoint
            await self._make_request("POST", "/api/market/wallet")
            logger.info("Bitkub authentication successful")

            return True

        except Exception as e:
            logger.error(f"Failed to connect to Bitkub exchange: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False

    async def disconnect(self):
        """Disconnect from Bitkub exchange."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Disconnected from Bitkub exchange")

    async def get_balance(self, currency: str = None) -> Dict[str, Balance]:
        """Get account balance from Bitkub."""
        try:
            result = await self._make_request("POST", "/api/market/wallet")
            wallet_data = result.get("result", {})

            balances = {}

            # Process all balances or specific currency
            for currency_code, balance_info in wallet_data.items():
                if currency and currency.upper() != currency_code.upper():
                    continue

                # Handle different balance formats
                if isinstance(balance_info, dict):
                    available = float(balance_info.get("available", 0))
                    reserved = float(balance_info.get("reserved", 0))
                else:
                    available = float(balance_info)
                    reserved = 0.0

                total = available + reserved

                balances[currency_code] = Balance(
                    currency=currency_code, free=available, used=reserved, total=total
                )

            return balances

        except Exception as e:
            logger.error(f"Failed to get Bitkub balance: {e}")
            return {}

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current market ticker from Bitkub."""
        try:
            # Get ticker for specific symbol
            result = await self._make_public_request("/api/market/ticker")
            ticker_data = result.get("result", {})

            if symbol not in ticker_data:
                raise Exception(f"Symbol {symbol} not found in ticker data")

            data = ticker_data[symbol]

            return Ticker(
                symbol=symbol,
                bid=float(data.get("highestBid", 0)),
                ask=float(data.get("lowestAsk", 0)),
                last=float(data.get("last", 0)),
                volume=float(data.get("baseVolume", 0)),
                timestamp=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Failed to get Bitkub ticker for {symbol}: {e}")
            raise

    async def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float = None,
        order_type: str = "market",
    ) -> OrderResult:
        """Place a trading order on Bitkub.

        ``amount`` is always a base-asset quantity (the ``BaseExchange``
        contract); ``bitkub_order_payload`` converts buys to THB.
        """
        try:
            endpoint = "/api/market/place-bid" if side.lower() == "buy" else "/api/market/place-ask"
            reference_price = 0.0
            if order_type != "limit":
                ticker = await self.get_ticker(symbol)
                reference_price = ticker.ask if side.lower() == "buy" else ticker.bid
                reference_price = reference_price or ticker.last
            order_data = bitkub_order_payload(
                symbol, side, amount, reference_price, order_type=order_type, limit_price=price
            )

            result = await self._make_request("POST", endpoint, order_data)
            order_result = result.get("result", {})

            return OrderResult(
                order_id=str(order_result.get("id", "")),
                symbol=symbol,
                side=side,
                amount=amount,
                price=price or 0,
                status="pending",  # Bitkub orders start as pending
                filled_amount=0.0,
                fees=0.0,
                timestamp=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Failed to place Bitkub order: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order on Bitkub."""
        try:
            data = {
                "sym": symbol,
                "id": order_id,
                "sd": "buy",  # We need to specify side, try both if needed
            }

            # Try cancelling as buy order first
            try:
                await self._make_request("POST", "/api/market/cancel-order", data)
                return True
            except Exception:
                # If failed, try as sell order
                data["sd"] = "sell"
                await self._make_request("POST", "/api/market/cancel-order", data)
                return True

        except Exception as e:
            logger.error(f"Failed to cancel Bitkub order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Get status of an existing order on Bitkub."""
        try:
            # Get order history and find the specific order
            orders = await self.get_order_history(symbol, limit=100)

            for order in orders:
                if order.order_id == order_id:
                    return order

            raise Exception(f"Order {order_id} not found")

        except Exception as e:
            logger.error(f"Failed to get Bitkub order status for {order_id}: {e}")
            raise

    async def get_open_orders(self, symbol: str = None) -> List[OrderResult]:
        """Get all open orders from Bitkub."""
        try:
            data = {}
            if symbol:
                data["sym"] = symbol

            result = await self._make_request(
                "POST", "/api/market/my-open-orders", data
            )
            orders_data = result.get("result", [])

            orders = []
            for order_data in orders_data:
                orders.append(
                    OrderResult(
                        order_id=str(order_data.get("id", "")),
                        symbol=order_data.get("sym", ""),
                        side=order_data.get("side", ""),
                        amount=float(order_data.get("amount", 0)),
                        price=float(order_data.get("rate", 0)),
                        status="open",
                        filled_amount=float(order_data.get("filled", 0)),
                        fees=float(order_data.get("fee", 0)),
                        timestamp=datetime.fromtimestamp(
                            order_data.get("ts", 0) / 1000
                        ),
                    )
                )

            return orders

        except Exception as e:
            logger.error(f"Failed to get Bitkub open orders: {e}")
            return []

    async def get_order_history(
        self, symbol: str = None, limit: int = 100
    ) -> List[OrderResult]:
        """Get order history from Bitkub."""
        try:
            data = {}
            if symbol:
                data["sym"] = symbol
            if limit:
                data["lmt"] = limit

            result = await self._make_request(
                "POST", "/api/market/my-order-history", data
            )
            orders_data = result.get("result", [])

            orders = []
            for order_data in orders_data:
                orders.append(
                    OrderResult(
                        order_id=str(order_data.get("id", "")),
                        symbol=order_data.get("sym", ""),
                        side=order_data.get("side", ""),
                        amount=float(order_data.get("amount", 0)),
                        price=float(order_data.get("rate", 0)),
                        status=order_data.get("status", ""),
                        filled_amount=float(order_data.get("filled", 0)),
                        fees=float(order_data.get("fee", 0)),
                        timestamp=datetime.fromtimestamp(
                            order_data.get("ts", 0) / 1000
                        ),
                    )
                )

            return orders

        except Exception as e:
            logger.error(f"Failed to get Bitkub order history: {e}")
            return []

    def get_supported_symbols(self) -> List[str]:
        """Get list of supported trading symbols on Bitkub."""
        return self.supported_symbols.copy()

    def get_market_type(self) -> str:
        """Get market type for Bitkub."""
        return "crypto"
