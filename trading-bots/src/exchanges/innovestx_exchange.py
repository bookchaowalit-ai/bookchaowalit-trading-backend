"""InnovestX exchange connector for Thai stock market."""

import aiohttp
import hashlib
import hmac
import time
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

from .base_exchange import BaseExchange, OrderResult, Balance, Ticker


class InnovestXExchange(BaseExchange):
    """InnovestX exchange connector for Thai stock trading."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.secret_key = config.get('secret_key')
        self.base_url = config.get('base_url', 'https://api.innovestxonline.com')
        self.environment = config.get('environment', 'sandbox')
        self.session: Optional[aiohttp.ClientSession] = None
        
        # InnovestX specific endpoints
        self.endpoints = {
            'account_info': '/api/v1/account/info',
            'balance': '/api/v1/account/balance',
            'market_data': '/api/v1/market/quote',
            'place_order': '/api/v1/order/place',
            'cancel_order': '/api/v1/order/cancel',
            'order_status': '/api/v1/order/status',
            'order_history': '/api/v1/order/history',
            'symbols': '/api/v1/market/symbols'
        }
    
    async def connect(self) -> bool:
        """Connect to InnovestX API."""
        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'TradingBot/1.0'
                }
            )
            
            # Test connection by getting account info
            account_info = await self._make_request('GET', self.endpoints['account_info'])
            
            if account_info and account_info.get('status') == 'success':
                logger.info(f"Connected to InnovestX ({self.environment})")
                return True
            else:
                logger.error("Failed to authenticate with InnovestX")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to InnovestX: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from InnovestX."""
        if self.session:
            await self.session.close()
            logger.info("Disconnected from InnovestX")
    
    def _generate_signature(self, method: str, endpoint: str, params: Dict = None, body: str = "") -> str:
        """Generate HMAC signature for InnovestX API."""
        timestamp = str(int(time.time() * 1000))
        
        # Create string to sign
        if params:
            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            string_to_sign = f"{method}{endpoint}?{query_string}{timestamp}{body}"
        else:
            string_to_sign = f"{method}{endpoint}{timestamp}{body}"
        
        # Generate signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature, timestamp
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Dict = None, 
        data: Dict = None
    ) -> Dict[str, Any]:
        """Make authenticated request to InnovestX API."""
        try:
            url = f"{self.base_url}{endpoint}"
            body = json.dumps(data) if data else ""
            
            # Generate signature
            signature, timestamp = self._generate_signature(method, endpoint, params, body)
            
            headers = {
                'X-API-KEY': self.api_key,
                'X-SIGNATURE': signature,
                'X-TIMESTAMP': timestamp,
                'Content-Type': 'application/json'
            }
            
            async with self.session.request(
                method=method,
                url=url,
                params=params,
                data=body if data else None,
                headers=headers
            ) as response:
                
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"InnovestX API error {response.status}: {error_text}")
                    return {}
                    
        except Exception as e:
            logger.error(f"InnovestX request failed: {e}")
            return {}
    
    async def get_balance(self, currency: str = None) -> Dict[str, Balance]:
        """Get account balance from InnovestX."""
        try:
            response = await self._make_request('GET', self.endpoints['balance'])
            
            if not response or response.get('status') != 'success':
                return {}
            
            balances = {}
            balance_data = response.get('data', {})
            
            # InnovestX typically returns THB balance and buying power
            if 'cash_balance' in balance_data:
                balances['THB'] = Balance(
                    currency='THB',
                    free=float(balance_data.get('available_cash', 0.0)),
                    used=float(balance_data.get('used_cash', 0.0)),
                    total=float(balance_data.get('cash_balance', 0.0))
                )
            
            # Add stock positions as balances
            positions = balance_data.get('positions', [])
            for position in positions:
                symbol = position.get('symbol')
                if symbol:
                    balances[symbol] = Balance(
                        currency=symbol,
                        free=float(position.get('available_quantity', 0.0)),
                        used=float(position.get('locked_quantity', 0.0)),
                        total=float(position.get('total_quantity', 0.0))
                    )
            
            return balances
            
        except Exception as e:
            logger.error(f"Failed to get InnovestX balance: {e}")
            return {}
    
    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current market ticker from InnovestX."""
        try:
            params = {'symbol': symbol}
            response = await self._make_request('GET', self.endpoints['market_data'], params=params)
            
            if not response or response.get('status') != 'success':
                raise Exception(f"Failed to get ticker for {symbol}")
            
            data = response.get('data', {})
            
            return Ticker(
                symbol=symbol,
                bid=float(data.get('bid', 0.0)),
                ask=float(data.get('ask', 0.0)),
                last=float(data.get('last_price', 0.0)),
                volume=float(data.get('volume', 0.0)),
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to get InnovestX ticker for {symbol}: {e}")
            raise
    
    async def place_order(
        self, 
        symbol: str, 
        side: str, 
        amount: float, 
        price: float = None,
        order_type: str = "market"
    ) -> OrderResult:
        """Place a trading order on InnovestX."""
        try:
            # Convert amount to integer (Thai stocks trade in whole shares)
            quantity = int(amount)
            
            order_data = {
                'symbol': symbol,
                'side': side.upper(),  # BUY or SELL
                'quantity': quantity,
                'order_type': order_type.upper()  # MARKET or LIMIT
            }
            
            if order_type.lower() == 'limit' and price:
                order_data['price'] = float(price)
            
            response = await self._make_request('POST', self.endpoints['place_order'], data=order_data)
            
            if not response or response.get('status') != 'success':
                raise Exception(f"Order placement failed: {response.get('message', 'Unknown error')}")
            
            order_info = response.get('data', {})
            
            return OrderResult(
                order_id=str(order_info.get('order_id')),
                symbol=symbol,
                side=side,
                amount=float(quantity),
                price=float(order_info.get('price', price or 0.0)),
                status=self._map_order_status(order_info.get('status', 'pending')),
                filled_amount=float(order_info.get('filled_quantity', 0.0)),
                fees=float(order_info.get('fees', 0.0)),
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to place InnovestX order: {e}")
            raise
    
    def _map_order_status(self, innovestx_status: str) -> str:
        """Map InnovestX order status to standard status."""
        status_mapping = {
            'NEW': 'pending',
            'PARTIALLY_FILLED': 'partial',
            'FILLED': 'filled',
            'CANCELED': 'cancelled',
            'REJECTED': 'cancelled',
            'EXPIRED': 'cancelled'
        }
        return status_mapping.get(innovestx_status.upper(), 'pending')
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order on InnovestX."""
        try:
            cancel_data = {
                'order_id': order_id,
                'symbol': symbol
            }
            
            response = await self._make_request('POST', self.endpoints['cancel_order'], data=cancel_data)
            
            if response and response.get('status') == 'success':
                logger.info(f"Cancelled InnovestX order {order_id}")
                return True
            else:
                logger.error(f"Failed to cancel InnovestX order {order_id}: {response.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to cancel InnovestX order {order_id}: {e}")
            return False
    
    async def get_order_status(self, order_id: str, symbol: str) -> OrderResult:
        """Get status of an existing order on InnovestX."""
        try:
            params = {
                'order_id': order_id,
                'symbol': symbol
            }
            
            response = await self._make_request('GET', self.endpoints['order_status'], params=params)
            
            if not response or response.get('status') != 'success':
                raise Exception(f"Failed to get order status for {order_id}")
            
            order_info = response.get('data', {})
            
            return OrderResult(
                order_id=order_id,
                symbol=symbol,
                side=order_info.get('side', '').lower(),
                amount=float(order_info.get('quantity', 0.0)),
                price=float(order_info.get('price', 0.0)),
                status=self._map_order_status(order_info.get('status', 'unknown')),
                filled_amount=float(order_info.get('filled_quantity', 0.0)),
                fees=float(order_info.get('fees', 0.0)),
                timestamp=datetime.fromisoformat(order_info.get('created_at', datetime.now().isoformat()))
            )
            
        except Exception as e:
            logger.error(f"Failed to get InnovestX order status: {e}")
            raise
    
    async def get_open_orders(self, symbol: str = None) -> List[OrderResult]:
        """Get all open orders from InnovestX."""
        try:
            params = {'status': 'OPEN'}
            if symbol:
                params['symbol'] = symbol
            
            response = await self._make_request('GET', self.endpoints['order_history'], params=params)
            
            if not response or response.get('status') != 'success':
                return []
            
            orders = response.get('data', [])
            
            return [
                OrderResult(
                    order_id=str(order.get('order_id')),
                    symbol=order.get('symbol'),
                    side=order.get('side', '').lower(),
                    amount=float(order.get('quantity', 0.0)),
                    price=float(order.get('price', 0.0)),
                    status=self._map_order_status(order.get('status', 'unknown')),
                    filled_amount=float(order.get('filled_quantity', 0.0)),
                    fees=float(order.get('fees', 0.0)),
                    timestamp=datetime.fromisoformat(order.get('created_at', datetime.now().isoformat()))
                )
                for order in orders
            ]
            
        except Exception as e:
            logger.error(f"Failed to get InnovestX open orders: {e}")
            return []
    
    async def get_order_history(self, symbol: str = None, limit: int = 100) -> List[OrderResult]:
        """Get order history from InnovestX."""
        try:
            params = {'limit': limit}
            if symbol:
                params['symbol'] = symbol
            
            response = await self._make_request('GET', self.endpoints['order_history'], params=params)
            
            if not response or response.get('status') != 'success':
                return []
            
            orders = response.get('data', [])
            
            return [
                OrderResult(
                    order_id=str(order.get('order_id')),
                    symbol=order.get('symbol'),
                    side=order.get('side', '').lower(),
                    amount=float(order.get('quantity', 0.0)),
                    price=float(order.get('price', 0.0)),
                    status=self._map_order_status(order.get('status', 'unknown')),
                    filled_amount=float(order.get('filled_quantity', 0.0)),
                    fees=float(order.get('fees', 0.0)),
                    timestamp=datetime.fromisoformat(order.get('created_at', datetime.now().isoformat()))
                )
                for order in orders
            ]
            
        except Exception as e:
            logger.error(f"Failed to get InnovestX order history: {e}")
            return []
    
    def get_supported_symbols(self) -> List[str]:
        """Get list of supported trading symbols on InnovestX."""
        # This would typically be cached from a symbols endpoint
        # Common Thai stocks
        return [
            'PTT', 'CPALL', 'KBANK', 'SCB', 'BBL', 'ADVANC', 'AOT', 'INTUCH',
            'TRUE', 'SCC', 'TCAP', 'TU', 'DTAC', 'EGCO', 'RATCH', 'BEM',
            'CPN', 'HMPRO', 'MINT', 'OSP', 'BANPU', 'PTTEP', 'PTTGC', 'IVL',
            'TOP', 'GPSC', 'EA', 'GULF', 'WHA', 'LH', 'COM7', 'CENTEL'
        ]
    
    def get_market_type(self) -> str:
        """Get market type for InnovestX."""
        return "stock"
    
    async def get_symbols_info(self) -> List[Dict[str, Any]]:
        """Get detailed information about available symbols."""
        try:
            response = await self._make_request('GET', self.endpoints['symbols'])
            
            if response and response.get('status') == 'success':
                return response.get('data', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Failed to get InnovestX symbols info: {e}")
            return []