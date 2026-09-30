# Upgrade Plan

## Current state

**Score: 4.5 / 10** (4 after pass 1, 2 before). Bitkub order units are now explicit and tested. A prototype multi-exchange bot
runner. It now has offline tests, CI, and paper mode enforced for every
connector. It is still unfit for real money (see P0).

## Backlog

### P0
- **Rotate the Neon database password.** An unredacted `npg_...` password
  sits in git history (commit `b9b30ce`, `NEON_MIGRATION_COMPLETE.md`). The
  HEAD redaction does not remove it from history.
- Strategies seed from ticks captured once a minute, not from OHLCV. Fetch
  real klines (for example ccxt `fetch_ohlcv`) so indicators see true bars.

### P1
- Bitkub connector still targets the legacy `THB_BTC` symbols and v1/v2
  endpoints; confirm against the current Bitkub API (v3 uses `btc_thb`) with
  a recorded fixture before any live use. Market-buy THB is derived from the
  current ask, so the filled base quantity can differ slightly; reconcile
  fills from the order history.
- Momentum and Thai-stock strategies size positions from a hard-coded
  balance (10k / 100k). Pass the real (or paper) balance in.
- `GridTradingStrategy.update_grid_after_fill` is never called, so grid
  levels never re-arm after a fill.
- Move money math to `Decimal` at the exchange boundary, with lot-size and
  tick-size rounding.
- Make `DatabaseManager` injectable instead of connecting in
  `TradingBot.__init__`.

### P2
- Clean up the ruff/pyupgrade backlog and widen the CI lint scope.
- Remove the unused `ta-lib`, `pandas-ta`, `alpaca` and `oanda` pins, or wire
  them up.

## Done in this pass (pass 1)
- Real orders now need an explicit `TRADING_MODE=live`. Every connector is
  otherwise wrapped by `PaperExchange`. Before this, Binance TH, Bitkub and
  InnovestX sent real signed orders in "paper" mode.
- Removed the fabricated random 100-bar history the bot traded on. That code
  also crashed on pandas 2 (`pd.np`).
- Grid order size is now a quote notional converted to a base quantity.
  Before, `base_order_size: 50` bought 50 BTC.
- Spot long-only accounting: no sells without inventory, sells are clamped to
  the held amount, buys aggregate into one position, and realized PnL
  includes fees. Fixed the dict-mutation crash in `_manage_positions`.
- Untracked the committed `.pyc` files and logs. Added offline pytest suite
  (27 tests), `requirements-test.txt`, and a GitHub Actions CI workflow.

## Done in this pass (pass 2)
- Bitkub units made explicit: `bitkub_order_payload()` in
  `src/exchanges/bitkub_exchange.py` takes a base-asset quantity (the
  `BaseExchange` contract) and sends `amt` in THB for `place-bid`
  (`qty * limit rate` or `qty * current ask`) and in base units for
  `place-ask`. Amounts round down (THB 2 dp, base 8 dp), sub-10 THB orders,
  non-positive amounts and unknown sides/types are rejected.
- `tests/test_bitkub_units.py` (15 tests, offline, network layer replaced):
  conversion, rounding, rejection, connector request bodies, and that paper
  mode never reaches the Bitkub order endpoint while debiting THB with the
  same unit rule. Full suite: 41 passed; ruff clean on the touched files
  (also removed an unused import and a bare `except`). No live orders were
  placed and no credentials were used.
