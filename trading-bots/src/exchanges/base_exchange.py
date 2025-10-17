"""Base exchange interface for trading bots."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


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