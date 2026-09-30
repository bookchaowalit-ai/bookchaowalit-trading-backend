"""Buy fees belong in the cost basis; sell fees come off the proceeds.

Before this, ``entry_price`` was the raw fill price, so every realized PnL
was overstated by the buy fee (paper and live alike).
"""

import pandas as pd
import pytest

import src.bot as bot_module
from src.exchanges.base_exchange import OrderResult, fee_to_quote, order_fee_in_quote
from src.exchanges.binance_exchange import _order_result
from src.exchanges.binance_th_exchange import fills_fee_in_quote
from src.exchanges.paper_exchange import PaperExchange
from src.strategies.base_strategy import Signal
from src.strategies.grid_strategy import GridTradingStrategy
from tests.fakes import FakeDB, FakeMarketExchange


class _NoDB:
    def __init__(self):
        pass


class _FeeInBaseExchange(FakeMarketExchange):
    """Live-style fills: buy commission in the base asset, sell in quote."""

    def __init__(self, prices, rate=0.001):
        super().__init__(prices)
        self.rate = rate

    async def place_order(self, symbol, side, amount, price=None, order_type="market"):
        fill = self.prices[symbol]
        base, quote = symbol.split("/")
        if side == "buy":
            fee, cur = amount * self.rate, base
        else:
            fee, cur = amount * fill * self.rate, quote
        return OrderResult(
            order_id="live", symbol=symbol, side=side, amount=amount, price=fill,
            status="filled", filled_amount=amount, fees=fee, fee_currency=cur,
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
async def test_paper_round_trip_pnl_equals_quote_balance_change(monkeypatch):
    inner = FakeMarketExchange({"BTC/USDT": 50_000.0})
    paper = PaperExchange(inner, starting_balances={"USDT": 10_000.0})
    b = _bot(monkeypatch, paper)

    await b._execute_signal(_signal("buy", 0.1, 50_000.0))
    # Flat market: the round trip loses exactly the two fees.
    await b._execute_signal(_signal("sell", 0.1, 50_000.0))

    pnl = b.db.trades[-1]["pnl"]
    assert pnl == pytest.approx(paper.balances["USDT"] - 10_000.0)
    assert pnl == pytest.approx(-(5.0 + 5.0))  # buy fee + sell fee, 0.1% of 5,000 each
    assert b.performance_metrics["winning_trades"] == 0


@pytest.mark.asyncio
async def test_close_position_path_also_counts_buy_fee(monkeypatch):
    inner = FakeMarketExchange({"BTC/USDT": 50_000.0})
    paper = PaperExchange(inner, starting_balances={"USDT": 10_000.0})
    b = _bot(monkeypatch, paper)

    await b._execute_signal(_signal("buy", 0.1, 50_000.0))
    await b._close_position(b.strategy.positions["BTC/USDT"])

    assert b.db.trades[-1]["pnl"] == pytest.approx(paper.balances["USDT"] - 10_000.0)


@pytest.mark.asyncio
async def test_live_buy_fee_in_base_asset_is_converted_into_cost_basis(monkeypatch):
    ex = _FeeInBaseExchange({"BTC/USDT": 50_000.0})
    b = _bot(monkeypatch, ex)

    await b._execute_signal(_signal("buy", 0.1, 50_000.0))
    pos = b.strategy.positions["BTC/USDT"]
    # 0.0001 BTC fee at 50,000 = 5 USDT on a 5,000 USDT purchase.
    assert pos.entry_price == pytest.approx((5_000.0 + 5.0) / 0.1)

    ex.prices["BTC/USDT"] = 51_000.0
    await b._execute_signal(_signal("sell", 0.1, 51_000.0))
    # gross 100, minus 5 buy fee, minus 5.1 sell fee (quote)
    assert b.db.trades[-1]["pnl"] == pytest.approx(100.0 - 5.0 - 5.1)


def test_fee_to_quote_units():
    assert fee_to_quote(2.0, "USDT", "BTC/USDT", 50_000.0) == 2.0
    assert fee_to_quote(2.0, None, "BTC/USDT", 50_000.0) == 2.0  # unknown -> quote convention
    assert fee_to_quote(0.001, "BTC", "BTC/USDT", 50_000.0) == pytest.approx(50.0)
    assert fee_to_quote(0.001, "btc", "THB_BTC", 2_000_000.0) == pytest.approx(2_000.0)
    # A third asset (BNB) cannot be priced here; never add it as if it were quote.
    assert fee_to_quote(0.01, "BNB", "BTC/USDT", 50_000.0) == 0.0
    assert fee_to_quote(float("nan"), "USDT", "BTC/USDT", 50_000.0) == 0.0


def test_ccxt_fee_in_base_is_reported_in_quote():
    order = {"id": "1", "symbol": "BTC/USDT", "side": "buy", "average": 50_000.0, "amount": 0.1,
             "filled": 0.1, "status": "closed", "fee": {"cost": 0.0001, "currency": "BTC"}}
    r = _order_result(order, "BTC/USDT", "buy")
    assert r.fee_currency == "USDT"
    assert r.fees == pytest.approx(5.0)
    assert order_fee_in_quote(r) == pytest.approx(5.0)

    multi = dict(order, fee=None, fees=[{"cost": 0.0001, "currency": "BTC"}, {"cost": 1.0, "currency": "USDT"}])
    assert _order_result(multi, "BTC/USDT", "buy").fees == pytest.approx(6.0)


def test_binance_th_fills_commission_asset_is_converted():
    fills = [
        {"price": "50000", "qty": "0.05", "commission": "0.00005", "commissionAsset": "BTC"},
        {"price": "50100", "qty": "0.05", "commission": "0.00005", "commissionAsset": "BTC"},
    ]
    assert fills_fee_in_quote(fills, "BTC/USDT") == pytest.approx(0.00005 * 50_000 + 0.00005 * 50_100)
    assert fills_fee_in_quote([{"price": "50000", "commission": "2.5", "commissionAsset": "USDT"}],
                              "BTC/USDT") == pytest.approx(2.5)
