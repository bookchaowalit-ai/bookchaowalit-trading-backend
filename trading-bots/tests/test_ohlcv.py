"""Strategies see closed exchange klines, not one tick per cycle (offline)."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

import src.bot as bot_module
from src.exchanges.base_exchange import closed_bars, ohlcv_frame, timeframe_seconds
from src.exchanges.binance_th_exchange import BinanceThExchange
from src.exchanges.paper_exchange import PaperExchange
from src.strategies.base_strategy import Signal
from src.strategies.grid_strategy import GridTradingStrategy
from tests.fakes import FakeDB, FakeMarketExchange

T0 = 1_780_000_000_000  # ms, aligned to a minute


def _rows(n, start=T0, step_ms=60_000):
    return [[start + i * step_ms, 100 + i, 101 + i, 99 + i, 100.5 + i, 10.0] for i in range(n)]


def test_timeframe_seconds():
    assert timeframe_seconds("1m") == 60
    assert timeframe_seconds("4h") == 14_400
    assert timeframe_seconds("1d") == 86_400
    for bad in ("", "m", "0m", "5x", "-1m"):
        with pytest.raises(ValueError):
            timeframe_seconds(bad)


def test_ohlcv_frame_parses_binance_klines_and_drops_bad_rows():
    raw = [
        [T0 + 60_000, "101", "102", "100", "101.5", "3", T0 + 119_999, "x"],
        [T0, "100", "101", "99", "100.5", "2", T0 + 59_999, "x"],
        [T0, "100", "101", "99", "100.7", "2", T0 + 59_999, "x"],  # duplicate: last wins
        [T0 + 120_000, "0", "1", "0", "1", "1"],  # non-positive price
        [T0 + 180_000, "10", "9", "11", "10", "1"],  # high < low
        ["bad", "1", "1", "1", "1", "1"],
        [T0 + 240_000, "1", "1"],  # too short
    ]
    df = ohlcv_frame(raw)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df["timestamp"].is_monotonic_increasing
    assert df.loc[0, "close"] == 100.7
    assert df.loc[0, "timestamp"] == pd.Timestamp(T0, unit="ms")
    assert df["close"].dtype == float


def test_ohlcv_frame_empty():
    assert ohlcv_frame([]).empty
    assert ohlcv_frame(None).empty


def test_closed_bars_drops_forming_candle():
    df = ohlcv_frame(_rows(3))
    last_open = pd.Timestamp(T0 + 120_000, unit="ms").to_pydatetime()
    # 30s into the third bar: it is still forming.
    assert len(closed_bars(df, "1m", last_open + timedelta(seconds=30))) == 2
    # Exactly at its close it counts as closed.
    assert len(closed_bars(df, "1m", last_open + timedelta(seconds=60))) == 3


class _KlineExchange(FakeMarketExchange):
    def __init__(self, prices, rows=None, fail=False):
        super().__init__(prices)
        self.rows = rows
        self.fail = fail
        self.calls = []

    async def get_ohlcv(self, symbol, timeframe="1m", limit=200):
        self.calls.append((symbol, timeframe, limit))
        if self.fail:
            raise RuntimeError("klines unavailable")
        return None if self.rows is None else ohlcv_frame(self.rows)


class _NoDB:
    pass


def _bot(monkeypatch, inner, config=None):
    monkeypatch.setattr(bot_module, "DatabaseManager", _NoDB)
    b = bot_module.TradingBot({"platform": "binance_th", "strategy": "grid", "symbols": ["BTC/USDT"],
                               "config": config or {}})
    b.db = FakeDB()
    b.strategy = GridTradingStrategy(b.config)
    b.exchange = PaperExchange(inner, starting_balances={"USDT": 10_000.0})
    return b


@pytest.mark.asyncio
async def test_bot_uses_closed_klines_through_paper_exchange(monkeypatch):
    now_ms = int(datetime.utcnow().timestamp() * 1000) // 60_000 * 60_000
    rows = _rows(30, start=now_ms - 29 * 60_000)  # last row is the forming bar
    inner = _KlineExchange({"BTC/USDT": 50_000.0}, rows=rows)
    b = _bot(monkeypatch, inner, {"timeframe": "1m", "ohlcv_limit": 50})

    await b._update_market_data("BTC/USDT")

    df = b.strategy.historical_data["BTC/USDT"]
    assert inner.calls == [("BTC/USDT", "1m", 50)]
    assert len(df) == 29  # forming bar excluded
    assert (df["high"] > df["low"]).all()  # real bars, not flat ticks
    assert inner.real_orders == []


@pytest.mark.asyncio
async def test_bot_falls_back_to_ticks_without_klines(monkeypatch):
    inner = _KlineExchange({"BTC/USDT": 50_000.0}, rows=None)
    b = _bot(monkeypatch, inner)
    await b._update_market_data("BTC/USDT")
    await b._update_market_data("BTC/USDT")
    df = b.strategy.historical_data["BTC/USDT"]
    assert len(df) == 2
    assert df["close"].tolist() == [50_000.0, 50_000.0]


@pytest.mark.asyncio
async def test_failed_kline_refresh_keeps_bars_and_never_mixes_ticks(monkeypatch):
    now_ms = int(datetime.utcnow().timestamp() * 1000) // 60_000 * 60_000
    inner = _KlineExchange({"BTC/USDT": 50_000.0}, rows=_rows(10, start=now_ms - 10 * 60_000))
    b = _bot(monkeypatch, inner)
    await b._update_market_data("BTC/USDT")
    before = b.strategy.historical_data["BTC/USDT"].copy()

    inner.fail = True
    await b._update_market_data("BTC/USDT")

    pd.testing.assert_frame_equal(b.strategy.historical_data["BTC/USDT"], before)


def test_invalid_timeframe_is_rejected(monkeypatch):
    monkeypatch.setattr(bot_module, "DatabaseManager", _NoDB)
    with pytest.raises(ValueError):
        bot_module.TradingBot({"platform": "binance_th", "config": {"timeframe": "banana"}})


@pytest.mark.asyncio
async def test_binance_th_get_ohlcv_maps_symbol_and_interval(monkeypatch):
    ex = BinanceThExchange({})
    seen = {}

    async def fake_klines(symbol, interval="1m", limit=100):
        seen.update(symbol=symbol, interval=interval, limit=limit)
        return [[T0, "1", "2", "0.5", "1.5", "7", T0 + 59_999]]

    monkeypatch.setattr(ex, "get_klines", fake_klines)
    df = await ex.get_ohlcv("BTC/USDT", timeframe="5m", limit=10)
    assert seen == {"symbol": "BTCUSDT", "interval": "5m", "limit": 10}
    assert df.loc[0, "volume"] == 7.0


class _CountingStrategy(GridTradingStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.analysed = []

    async def analyze(self, symbol, timeframe="1h"):
        self.analysed.append(self.historical_data[symbol]["timestamp"].iloc[-1])
        return Signal(action="buy", symbol=symbol, price=50_000.0, amount=0.001, confidence=1.0,
                      timestamp=datetime.utcnow())


@pytest.mark.asyncio
async def test_each_closed_bar_is_analysed_once(monkeypatch):
    # 4h bars: a 60 s cycle sees the same last closed bar many times.
    step = 4 * 3600 * 1000
    now_ms = int(datetime.utcnow().timestamp() * 1000) // step * step
    start = now_ms - 20 * step
    inner = _KlineExchange({"BTC/USDT": 50_000.0}, rows=_rows(19, start=start, step_ms=step))
    b = _bot(monkeypatch, inner, {"timeframe": "4h"})
    b.strategy = _CountingStrategy(b.config)

    for _ in range(3):
        await b._execute_trading_cycle()
    assert len(b.strategy.analysed) == 1
    assert len(b.exchange.orders) == 1, "the same bar must not trade on every cycle"
    assert inner.real_orders == []

    # The next bar closes: it is analysed exactly once.
    inner.rows = _rows(20, start=start, step_ms=step)
    for _ in range(3):
        await b._execute_trading_cycle()
    assert len(b.strategy.analysed) == 2
    assert b.strategy.analysed[1] - b.strategy.analysed[0] == pd.Timedelta(hours=4)

    # A forming bar is not a new closed bar.
    inner.rows = _rows(21, start=start, step_ms=step)
    await b._execute_trading_cycle()
    assert len(b.strategy.analysed) == 2


@pytest.mark.asyncio
async def test_tick_fallback_is_analysed_every_cycle(monkeypatch):
    inner = _KlineExchange({"BTC/USDT": 50_000.0}, rows=None)
    b = _bot(monkeypatch, inner)
    b.strategy = _CountingStrategy(b.config)
    await b._execute_trading_cycle()
    await b._execute_trading_cycle()
    assert len(b.strategy.analysed) == 2
