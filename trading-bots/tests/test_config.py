import pytest

from src.config import is_live_mode


@pytest.mark.parametrize("value", [None, "", "paper", "Paper", "papr", "LIVE-ish", "true"])
def test_anything_but_explicit_live_is_paper(value):
    assert is_live_mode(value) is False


@pytest.mark.parametrize("value", ["live", "LIVE", " live "])
def test_explicit_live_enables_real_orders(value):
    assert is_live_mode(value) is True
