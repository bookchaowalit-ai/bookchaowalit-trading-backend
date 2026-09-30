"""NaN/inf quantities and prices, and ccxt orders with null fields."""

import math

import pytest

from src.exchanges.binance_exchange import BinanceExchange
from src.exchanges.paper_exchange import PaperExchange, PaperOrderError
from tests.fakes import FakeMarketExchange
from tests.test_bot_execution import _signal, bot  # noqa: F401  (fixture)


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [math.nan, math.inf])
async def test_paper_rejects_non_finite_amount(amount):
    ex = PaperExchange(FakeMarketExchange({"BTC/USDT": 50_000.0}), starting_balances={"USDT": 1_000.0})
    with pytest.raises(PaperOrderError):
        await ex.place_order("BTC/USDT", "buy", amount)
    assert ex.balances == {"USDT": 1_000.0}


@pytest.mark.asyncio
async def test_paper_rejects_nan_ticker_price():
    ex = PaperExchange(FakeMarketExchange({"BTC/USDT": math.nan}), starting_balances={"USDT": 1_000.0})
    with pytest.raises(PaperOrderError):
        await ex.place_order("BTC/USDT", "buy", 0.01)
    assert ex.balances == {"USDT": 1_000.0}


@pytest.mark.asyncio
async def test_bot_ignores_nan_signal(bot):  # noqa: F811
    await bot._execute_signal(_signal("buy", math.nan))
    await bot._execute_signal(_signal("buy", 0.01, price=math.nan))
    assert bot.exchange.orders == []
    assert not any(math.isnan(v) for v in bot.exchange.balances.values())


class _FakeCcxt:
    """ccxt returns every unified key, with None for what Binance omitted."""

    def __init__(self, order):
        self.order = order

    async def create_market_order(self, symbol, side, amount):
        return dict(self.order)

    async def fetch_order(self, order_id, symbol):
        return dict(self.order)

    async def fetch_open_orders(self, symbol=None):
        return [dict(self.order)]


def _ccxt_market_fill(**overrides):
    order = {
        "id": "1", "symbol": "BTC/USDT", "side": "buy", "type": "market",
        "amount": 0.01, "filled": 0.01, "price": None, "average": 50_010.0,
        "status": "closed", "fee": None, "fees": [], "timestamp": 1_700_000_000_000,
    }
    order.update(overrides)
    return order


@pytest.mark.asyncio
async def test_binance_market_order_with_null_fee_and_price():
    ex = BinanceExchange({})
    ex.exchange = _FakeCcxt(_ccxt_market_fill())
    result = await ex.place_order("BTC/USDT", "buy", 0.01, price=50_000.0)
    # Used to raise AttributeError ('NoneType'.get) after the order was sent.
    assert result.price == 50_010.0  # average, the execution price
    assert result.fees == 0.0
    assert result.filled_amount == 0.01

    status = await ex.get_order_status("1", "BTC/USDT")
    assert status.price == 50_010.0 and status.fees == 0.0


@pytest.mark.asyncio
async def test_binance_fee_list_and_missing_average():
    ex = BinanceExchange({})
    ex.exchange = _FakeCcxt(_ccxt_market_fill(
        average=None, price=0, filled=None,
        fees=[{"cost": 0.02, "currency": "USDT"}, {"cost": 0.03, "currency": "USDT"}],
    ))
    result = await ex.place_order("BTC/USDT", "buy", 0.01, price=50_000.0)
    assert result.price == 50_000.0  # falls back to the reference price
    assert result.fees == pytest.approx(0.05)
    assert result.filled_amount == 0.0
    [open_order] = await ex.get_open_orders("BTC/USDT")
    assert open_order.fees == pytest.approx(0.05)
