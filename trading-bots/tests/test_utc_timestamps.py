"""Exchange epoch timestamps must be converted as UTC, not host-local time."""

import os
import re
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.exchanges.base_exchange import utc_from_ms, utc_now

EXCHANGES = Path(__file__).resolve().parents[1] / "src" / "exchanges"


@pytest.fixture
def bangkok_host():
    if not hasattr(time, "tzset"):
        pytest.skip("needs time.tzset")
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Bangkok"  # UTC+7, no DST
    time.tzset()
    yield
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def test_utc_from_ms_ignores_host_timezone(bangkok_host):
    assert utc_from_ms(1_700_000_000_000) == datetime(2023, 11, 14, 22, 13, 20)
    assert utc_from_ms(None) == datetime(1970, 1, 1)


def test_utc_now_is_naive_utc(bangkok_host):
    now = utc_now()
    assert now.tzinfo is None
    assert abs((now - utc_from_ms(time.time() * 1000)).total_seconds()) < 5


def test_no_exchange_uses_host_local_fromtimestamp():
    offenders = [
        f"{path.name}:{i}"
        for path in EXCHANGES.glob("*.py")
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"datetime\.fromtimestamp\(", line) and "tz=" not in line
    ]
    assert offenders == []
