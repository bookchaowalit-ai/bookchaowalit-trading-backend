# Upgrade Plan

## Current state

**Score: 4 / 10** (was 2 before pass 1). A prototype multi-exchange bot
runner. It now has offline tests, CI, and paper mode enforced for every
connector. It is still unfit for real money (see P0).

## Backlog

### P0
- **Rotate the Neon database password.** An unredacted `npg_...` password
  sits in git history (commit `b9b30ce`, `NEON_MIGRATION_COMPLETE.md`). The
  HEAD redaction does not remove it from history.
- The Bitkub connector sends `amt` for buys in THB (quote currency), while
  strategies emit base-asset quantities. Convert per exchange before
  `TRADING_MODE=live` is ever used with Bitkub.
- Strategies seed from ticks captured once a minute, not from OHLCV. Fetch
  real klines (for example ccxt `fetch_ohlcv`) so indicators see true bars.

### P1
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
