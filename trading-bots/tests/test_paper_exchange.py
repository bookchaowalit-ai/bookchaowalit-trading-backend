import pytest

from src.exchanges.paper_exchange import PaperExchange, PaperOrderError
from tests.fakes import FakeMarketExchange


@pytest.fixture
def paper():
    inner = FakeMarketExchange({"BTC/USDT": 50_000.0, "THB_BTC": 2_000_000.0})
    return PaperExchange(inner, starting_balances={"USDT": 1_000.0, "THB": 10_000.0}, fee_rate=0.001), inner


@pytest.mark.asyncio
async def test_market_buy_is_simulated_and_never_reaches_exchange(paper):
    ex, inner = paper
    result = await ex.place_order("BTC/USDT", "buy", 0.01)
    assert inner.real_orders == []
    assert result.status == "filled" and result.order_id.startswith("paper-")
    assert result.price == 50_000.0
    assert ex.balances["BTC"] == pytest.approx(0.01)
    assert ex.balances["USDT"] == pytest.approx(1_000 - 500 - 0.5)


@pytest.mark.asyncio
async def test_buy_beyond_balance_is_rejected(paper):
    ex, _ = paper
    with pytest.raises(PaperOrderError):
        await ex.place_order("BTC/USDT", "buy", 1.0)
    assert "BTC" not in ex.balances


@pytest.mark.asyncio
async def test_cannot_sell_what_is_not_held(paper):
    ex, _ = paper
    with pytest.raises(PaperOrderError):
        await ex.place_order("BTC/USDT", "sell", 0.001)


@pytest.mark.asyncio
async def test_bitkub_symbol_orientation(paper):
    ex, _ = paper
    await ex.place_order("THB_BTC", "buy", 0.001)
    assert ex.balances["BTC"] == pytest.approx(0.001)
    assert ex.balances["THB"] == pytest.approx(10_000 - 2_000 - 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [0, -1])
async def test_non_positive_amount_rejected(paper, amount):
    ex, _ = paper
    with pytest.raises(PaperOrderError):
        await ex.place_order("BTC/USDT", "buy", amount)


@pytest.mark.asyncio
async def test_balance_is_simulated(paper):
    ex, _ = paper
    balances = await ex.get_balance()
    assert balances["USDT"].free == 1_000.0
