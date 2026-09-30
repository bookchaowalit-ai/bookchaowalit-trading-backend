import pandas as pd
import pytest

from src.strategies.grid_strategy import GridTradingStrategy


def _df(price, n=25):
    return pd.DataFrame({"close": [price] * n})


def test_level_amount_is_quote_notional_converted_to_base_quantity():
    strat = GridTradingStrategy({"grid_levels": 4, "grid_spacing": 0.01, "base_order_size": 50, "max_position_size": 1000})
    strat._initialize_grid("BTC/USDT", 50_000.0)
    for level in strat.active_grids["BTC/USDT"]:
        # 50 USDT per level, never 50 BTC
        assert level["amount"] * level["price"] == pytest.approx(50.0)


def test_level_notional_is_capped_by_max_position_size():
    strat = GridTradingStrategy({"grid_levels": 2, "grid_spacing": 0.01, "base_order_size": 500, "max_position_size": 100})
    strat._initialize_grid("ETH/USDT", 2_000.0)
    for level in strat.active_grids["ETH/USDT"]:
        assert level["amount"] * level["price"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_holds_until_enough_real_history():
    strat = GridTradingStrategy({"grid_levels": 4, "grid_spacing": 0.01, "base_order_size": 50})
    strat.update_historical_data("BTC/USDT", _df(50_000.0, n=5))
    signal = await strat.analyze("BTC/USDT")
    assert signal.action == "hold"


@pytest.mark.asyncio
async def test_buy_level_triggers_once_with_sized_amount():
    strat = GridTradingStrategy({"grid_levels": 4, "grid_spacing": 0.01, "base_order_size": 50})
    strat.update_historical_data("BTC/USDT", _df(50_000.0))
    assert (await strat.analyze("BTC/USDT")).action == "hold"

    strat.update_historical_data("BTC/USDT", _df(49_400.0))
    signal = await strat.analyze("BTC/USDT")
    assert signal.action == "buy"
    assert signal.amount * signal.price == pytest.approx(50.0)
