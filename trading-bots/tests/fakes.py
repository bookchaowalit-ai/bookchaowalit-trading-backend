"""In-memory fakes: no network, no database."""

from datetime import datetime

from src.exchanges.base_exchange import BaseExchange, OrderResult, Ticker


class FakeMarketExchange(BaseExchange):
    """Serves tickers from a dict and fails loudly if a real order is attempted."""

    def __init__(self, prices):
        super().__init__({})
        self.prices = dict(prices)
        self.real_orders = []

    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def get_balance(self, currency=None):
        raise AssertionError("private endpoint must not be called in paper mode")

    async def get_ticker(self, symbol):
        p = self.prices[symbol]
        return Ticker(symbol=symbol, bid=p, ask=p, last=p, volume=1.0, timestamp=datetime.utcnow())

    async def place_order(self, symbol, side, amount, price=None, order_type="market"):
        self.real_orders.append((symbol, side, amount))
        return OrderResult(
            order_id="real", symbol=symbol, side=side, amount=amount,
            price=self.prices[symbol], status="filled", filled_amount=amount,
        )

    async def cancel_order(self, order_id, symbol):
        return True

    async def get_order_status(self, order_id, symbol):
        raise NotImplementedError

    async def get_open_orders(self, symbol=None):
        return []

    async def get_order_history(self, symbol=None, limit=100):
        return []

    def get_supported_symbols(self):
        return list(self.prices)

    def get_market_type(self):
        return "crypto"


class FakeDB:
    def __init__(self):
        self.trades = []

    async def insert_trade(self, trade):
        self.trades.append(trade)

    async def update_bot_status(self, *args, **kwargs):
        pass

    async def insert_bot_metrics(self, *args, **kwargs):
        pass
