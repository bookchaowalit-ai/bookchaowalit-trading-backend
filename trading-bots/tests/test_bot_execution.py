import pandas as pd
import pytest

import src.bot as bot_module
from src.exchanges.paper_exchange import PaperExchange
from src.strategies.base_strategy import Position, Signal
from src.strategies.grid_strategy import GridTradingStrategy
from tests.fakes import FakeDB, FakeMarketExchange


class _NoDB:
    def __init__(self):
        pass


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setattr(bot_module, "DatabaseManager", _NoDB)
    b = bot_module.TradingBot(
        {"id": "t", "name": "T", "platform": "binance_th", "strategy": "grid", "symbols": ["BTC/USDT"],
         "config": {"stop_loss": 0.03}}
    )
    b.db = FakeDB()
    b.strategy = GridTradingStrategy(b.config)
    inner = FakeMarketExchange({"BTC/USDT": 50_000.0})
    b.exchange = PaperExchange(inner, starting_balances={"USDT": 10_000.0})
    b._inner = inner
    return b


def _signal(action, amount, price=50_000.0):
    return Signal(action=action, symbol="BTC/USDT", price=price, amount=amount, confidence=1.0,
                  timestamp=pd.Timestamp.utcnow().to_pydatetime())


def test_paper_mode_wraps_every_platform(monkeypatch):
    monkeypatch.setattr(bot_module, "DatabaseManager", _NoDB)
    monkeypatch.setattr(bot_module.Config, "LIVE_TRADING", False)
    for platform in ("binance", "binance_th", "bitkub", "innovestx"):
        b = bot_module.TradingBot({"platform": platform})
        assert isinstance(b._create_exchange(), PaperExchange), platform


@pytest.mark.asyncio
async def test_sell_without_position_is_skipped(bot):
    await bot._execute_signal(_signal("sell", 0.01))
    assert bot.db.trades == []
    assert bot.exchange.orders == []


@pytest.mark.asyncio
async def test_buys_aggregate_into_one_position_and_sell_realizes_pnl(bot):
    await bot._execute_signal(_signal("buy", 0.01))
    bot._inner.prices["BTC/USDT"] = 40_000.0
    await bot._execute_signal(_signal("buy", 0.01, price=40_000.0))

    pos = bot.strategy.positions["BTC/USDT"]
    assert pos.amount == pytest.approx(0.02)
    buy_fees = (0.01 * 50_000 + 0.01 * 40_000) * 0.001
    # Cost basis carries the buy fees (quote currency).
    assert pos.entry_price == pytest.approx((900.0 + buy_fees) / 0.02)

    bot._inner.prices["BTC/USDT"] = 60_000.0
    await bot._execute_signal(_signal("sell", 1.0, price=60_000.0))  # clamped to held 0.02
    assert "BTC/USDT" not in bot.strategy.positions
    sell = bot.db.trades[-1]
    assert sell["amount"] == pytest.approx(0.02)
    fee = 0.02 * 60_000 * 0.001
    assert sell["pnl"] == pytest.approx((60_000 - 45_000) * 0.02 - fee - buy_fees)
    assert bot.performance_metrics["winning_trades"] == 1


@pytest.mark.asyncio
async def test_manage_positions_can_close_while_iterating(bot):
    await bot._execute_signal(_signal("buy", 0.01))
    bot.strategy.add_position(Position("ETH/USDT", "long", 0.0, 1.0, 1.0, 0.0, pd.Timestamp.utcnow()))
    bot._inner.prices["ETH/USDT"] = 1.0
    bot._inner.prices["BTC/USDT"] = 40_000.0  # > 3% stop loss
    await bot._manage_positions()
    assert "BTC/USDT" not in bot.strategy.positions


@pytest.mark.asyncio
async def test_market_data_uses_only_real_ticks(bot):
    await bot._update_market_data("BTC/USDT")
    await bot._update_market_data("BTC/USDT")
    df = bot.strategy.historical_data["BTC/USDT"]
    assert len(df) == 2
    assert (df["close"] == 50_000.0).all()


@pytest.mark.asyncio
async def test_invalid_signal_is_ignored(bot):
    await bot._execute_signal(_signal("buy", 0.0))
    await bot._execute_signal(_signal("buy", 0.01, price=0.0))
    assert bot.exchange.orders == []
