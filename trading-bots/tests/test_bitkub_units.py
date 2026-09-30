"""Bitkub unit conversion: strategies speak base units, Bitkub bids speak THB.

Offline only: the connector's HTTP layer is replaced; nothing is sent and no
credentials are used.
"""

from datetime import datetime

import pytest

from src.exchanges.base_exchange import Ticker
from src.exchanges.bitkub_exchange import BitkubExchange, bitkub_order_payload
from src.exchanges.paper_exchange import PaperExchange


def test_buy_amt_is_thb_notional_of_the_base_quantity():
    body = bitkub_order_payload("THB_BTC", "buy", 0.001, reference_price=2_000_000.0)
    assert body == {"sym": "THB_BTC", "amt": 2_000.0, "typ": "market", "rat": 0}


def test_sell_amt_stays_in_base_units():
    body = bitkub_order_payload("THB_BTC", "sell", 0.001, reference_price=2_000_000.0)
    assert body["amt"] == pytest.approx(0.001)
    assert body["rat"] == 0


def test_limit_buy_converts_with_the_limit_rate_not_the_market():
    body = bitkub_order_payload(
        "THB_ETH", "buy", 0.5, reference_price=999_999.0, order_type="limit", limit_price=100_000.0
    )
    assert body == {"sym": "THB_ETH", "amt": 50_000.0, "typ": "limit", "rat": 100_000.0}


def test_amounts_round_down_never_up():
    # 0.0012345 BTC * 1,234,567.89 THB = 1524.0740... THB -> 1524.07
    buy = bitkub_order_payload("THB_BTC", "buy", 0.0012345, reference_price=1_234_567.89)
    assert buy["amt"] == 1524.07
    sell = bitkub_order_payload("THB_BTC", "sell", 0.123456789, reference_price=1_000_000.0)
    assert sell["amt"] == 0.12345678


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_amount": 0, "reference_price": 1_000.0},
        {"base_amount": -1, "reference_price": 1_000.0},
        {"base_amount": 1, "reference_price": 0},
        {"base_amount": 1, "reference_price": 1_000.0, "order_type": "limit", "limit_price": None},
        {"base_amount": 1, "reference_price": 1_000.0, "order_type": "stop"},
        {"base_amount": 0.000001, "reference_price": 2_000_000.0},  # 2 THB < 10 THB minimum
    ],
)
def test_invalid_orders_are_rejected(kwargs):
    with pytest.raises(ValueError):
        bitkub_order_payload("THB_BTC", "buy", **kwargs)


def test_unknown_side_rejected():
    with pytest.raises(ValueError):
        bitkub_order_payload("THB_BTC", "short", 1, reference_price=1_000.0)


class RecordingBitkub(BitkubExchange):
    """Bitkub connector whose network layer is replaced by a recorder."""

    def __init__(self, price):
        super().__init__({"apiKey": "unused", "secret": "unused"})
        self.price = price
        self.requests = []

    async def get_ticker(self, symbol):
        p = self.price
        return Ticker(symbol=symbol, bid=p * 0.999, ask=p, last=p, volume=1.0, timestamp=datetime.utcnow())

    async def _make_request(self, method, endpoint, data=None):
        self.requests.append((endpoint, data))
        return {"error": 0, "result": {"id": 1}}


@pytest.mark.asyncio
async def test_connector_market_buy_sends_thb_using_the_ask():
    ex = RecordingBitkub(price=2_000_000.0)
    result = await ex.place_order("THB_BTC", "buy", 0.001)
    endpoint, body = ex.requests[0]
    assert endpoint == "/api/market/place-bid"
    assert body["amt"] == 2_000.0
    assert result.amount == 0.001  # the result stays in base units


@pytest.mark.asyncio
async def test_connector_market_sell_sends_base_quantity():
    ex = RecordingBitkub(price=2_000_000.0)
    await ex.place_order("THB_BTC", "sell", 0.001)
    endpoint, body = ex.requests[0]
    assert endpoint == "/api/market/place-ask"
    assert body["amt"] == pytest.approx(0.001)


@pytest.mark.asyncio
async def test_paper_mode_never_reaches_the_bitkub_order_endpoint():
    inner = RecordingBitkub(price=2_000_000.0)
    paper = PaperExchange(inner, starting_balances={"THB": 10_000.0}, fee_rate=0.0025)
    await paper.place_order("THB_BTC", "buy", 0.001)
    assert inner.requests == []
    # Paper accounting uses the same unit rule: THB debited = base qty * price.
    assert paper.balances["BTC"] == pytest.approx(0.001)
    assert paper.balances["THB"] == pytest.approx(10_000 - 2_000 - 5)
