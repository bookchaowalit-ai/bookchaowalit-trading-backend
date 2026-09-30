"""Base-asset buy fees shrink holdings; Binance TH market fills report price 0.

Offline: the Binance TH network layer is replaced, and the bot tests use an
in-memory exchange. No credentials, no real orders.
"""

import pandas as pd
import pytest

import src.bot as bot_module
from src.exchanges.base_exchange import OrderResult, net_base_received
from src.exchanges.binance_exchange import _order_result
from src.exchanges.binance_th_exchange import BinanceThExchange, order_fill_price
from src.strategies.base_strategy import Signal
from src.strategies.grid_strategy import GridTradingStrategy
from tests.fakes import FakeDB, FakeMarketExchange


class _NoDB:
    def __init__(self):
        pass


class _BaseFeeLedger(FakeMarketExchange):
    """Live-like venue: withholds the buy commission from the coins and
    refuses to sell more than the account holds."""

    def __init__(self, prices, rate=0.001):
        super().__init__(prices)
        self.rate = rate
        self.coins = 0.0

    async def place_order(self, symbol, side, amount, price=None, order_type="market"):
        fill = self.prices[symbol]
        base, quote = symbol.split("/")
        if side == "buy":
            fee = amount * self.rate
            self.coins += amount - fee
            return OrderResult(
                order_id="b", symbol=symbol, side=side, amount=amount, price=fill, status="filled",
                filled_amount=amount, fees=fee * fill, fee_currency=quote, base_fee=fee,
            )
        if amount > self.coins + 1e-12:
            raise AssertionError(f"insufficient balance: sell {amount} > held {self.coins}")
        self.coins -= amount
        return OrderResult(
            order_id="s", symbol=symbol, side=side, amount=amount, price=fill, status="filled",
            filled_amount=amount, fees=amount * fill * self.rate, fee_currency=quote,
        )


def _bot(monkeypatch, exchange):
    monkeypatch.setattr(bot_module, "DatabaseManager", _NoDB)
    b = bot_module.TradingBot(
        {"id": "t", "name": "T", "platform": "binance", "strategy": "grid", "symbols": ["BTC/USDT"],
         "config": {"stop_loss": 0.5}}
    )
    b.db = FakeDB()
    b.strategy = GridTradingStrategy(b.config)
    b.exchange = exchange
    return b


def _signal(action, amount, price):
    return Signal(action=action, symbol="BTC/USDT", price=price, amount=amount, confidence=1.0,
                  timestamp=pd.Timestamp.utcnow().to_pydatetime())


@pytest.mark.asyncio
async def test_tracked_amount_is_net_of_base_fee_and_sell_never_exceeds_holdings(monkeypatch):
    ex = _BaseFeeLedger({"BTC/USDT": 50_000.0})
    b = _bot(monkeypatch, ex)

    await b._execute_signal(_signal("buy", 0.1, 50_000.0))
    await b._execute_signal(_signal("buy", 0.1, 50_000.0))
    pos = b.strategy.positions["BTC/USDT"]
    assert pos.amount == pytest.approx(ex.coins) == pytest.approx(0.1998)
    # Cost basis: 10,000 USDT spent for 0.1998 BTC (fee already inside).
    assert pos.entry_price == pytest.approx(10_000.0 / 0.1998)

    await b._execute_signal(_signal("sell", 1.0, 50_000.0))
    assert b.db.trades[-1]["side"] == "sell"  # the sell went through, not rejected
    assert ex.coins == pytest.approx(0.0, abs=1e-12)
    assert "BTC/USDT" not in b.strategy.positions


@pytest.mark.asyncio
async def test_close_position_after_base_fee_buy_sells_only_what_is_held(monkeypatch):
    ex = _BaseFeeLedger({"BTC/USDT": 50_000.0})
    b = _bot(monkeypatch, ex)

    await b._execute_signal(_signal("buy", 0.1, 50_000.0))
    await b._close_position(b.strategy.positions["BTC/USDT"])
    assert b.db.trades[-1]["amount"] == pytest.approx(0.0999)
    assert ex.coins == pytest.approx(0.0, abs=1e-12)


def test_net_base_received_units():
    quote_fee = OrderResult("1", "BTC/USDT", "buy", 0.1, 50_000.0, "filled", filled_amount=0.1,
                            fees=5.0, fee_currency="USDT")
    assert net_base_received(quote_fee) == pytest.approx(0.1)
    base_fee = OrderResult("1", "BTC/USDT", "buy", 0.1, 50_000.0, "filled", filled_amount=0.1,
                           fees=0.0001, fee_currency="BTC")
    assert net_base_received(base_fee) == pytest.approx(0.0999)
    partial = OrderResult("1", "BTC/USDT", "buy", 0.1, 50_000.0, "partial", filled_amount=0.04,
                          fees=0.2, fee_currency="USDT", base_fee=0.00004)
    assert net_base_received(partial) == pytest.approx(0.03996)


def test_ccxt_base_fee_is_kept_in_base_units():
    order = {"id": "1", "symbol": "BTC/USDT", "side": "buy", "average": 50_000.0, "amount": 0.1,
             "filled": 0.1, "status": "closed", "fee": {"cost": 0.0001, "currency": "BTC"}}
    r = _order_result(order, "BTC/USDT", "buy")
    assert r.base_fee == pytest.approx(0.0001)
    assert net_base_received(r) == pytest.approx(0.0999)
    bnb = dict(order, fee={"cost": 0.01, "currency": "BNB"})
    assert net_base_received(_order_result(bnb, "BTC/USDT", "buy")) == pytest.approx(0.1)


def test_binance_th_fill_price_sources():
    fills = [{"price": "50000", "qty": "0.03"}, {"price": "50100", "qty": "0.01"}]
    assert order_fill_price({"price": "0.00000000", "fills": fills}, 1.0) == pytest.approx(
        (50_000 * 0.03 + 50_100 * 0.01) / 0.04
    )
    assert order_fill_price({"price": "0", "cummulativeQuoteQty": "5010", "executedQty": "0.1"}, 1.0) == (
        pytest.approx(50_100.0)
    )
    assert order_fill_price({"price": "49000", "executedQty": "0"}, 1.0) == 49_000.0
    assert order_fill_price({"price": "0.00000000", "executedQty": "0"}, 50_000.0) == 50_000.0


@pytest.mark.asyncio
async def test_binance_th_market_order_price_is_never_zero():
    ex = BinanceThExchange({"apiKey": None, "secret": None})

    responses = [
        {"orderId": 1, "status": "FILLED", "price": "0.00000000", "executedQty": "0.10000000",
         "cummulativeQuoteQty": "5005.00000000", "transactTime": 0,
         "fills": [{"price": "50000", "qty": "0.05", "commission": "0.00005", "commissionAsset": "BTC"},
                   {"price": "50100", "qty": "0.05", "commission": "0.00005", "commissionAsset": "BTC"}]},
        {"orderId": 2, "status": "FILLED", "price": "0.00000000", "executedQty": "0.10000000",
         "cummulativeQuoteQty": "5005.00000000", "transactTime": 0},
        {"orderId": 3, "status": "NEW", "price": "0.00000000", "executedQty": "0.00000000",
         "cummulativeQuoteQty": "0.00000000", "transactTime": 0},
    ]

    async def fake_request(method, endpoint, params=None, signed=False):
        assert (method, endpoint) == ("POST", "/api/v1/order")
        return responses.pop(0)

    ex._make_request = fake_request

    r = await ex.place_order("BTC/USDT", "buy", 0.1, price=49_900.0)
    assert r.price == pytest.approx(50_050.0)
    assert r.base_fee == pytest.approx(0.0001)
    assert net_base_received(r) == pytest.approx(0.0999)

    r = await ex.place_order("BTC/USDT", "buy", 0.1, price=49_900.0)
    assert r.price == pytest.approx(50_050.0)

    r = await ex.place_order("BTC/USDT", "buy", 0.1, price=49_900.0)
    assert r.price == 49_900.0
