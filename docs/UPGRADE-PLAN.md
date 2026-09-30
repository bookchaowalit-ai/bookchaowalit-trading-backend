# Upgrade Plan

## Current state

**Score: 5.5 / 10** (5 after pass 3, 4.5 after pass 2, 4 after pass 1, 2 before). Each closed bar is now analysed once, so long timeframes no longer repeat the same signal every 60 s cycle. Strategies now analyse closed exchange klines instead of one tick per minute. A prototype multi-exchange bot
runner. It now has offline tests, CI, and paper mode enforced for every
connector. It is still unfit for real money (see P0).

## Backlog

### P0
- **Rotate the Neon database password.** An unredacted `npg_...` password
  sits in git history (commit `b9b30ce`, `NEON_MIGRATION_COMPLETE.md`). The
  HEAD redaction does not remove it from history.

### P1
- Klines for Bitkub (`/tradingview/history`) and InnovestX so they stop
  falling back to one tick per cycle; record a fixture per exchange first.
- Optional: align the 60 s cycle to the `timeframe` close to cut signal
  latency (repeat evaluation of a closed bar is already prevented).
- Bitkub connector still targets the legacy `THB_BTC` symbols and
  unversioned `/api/market/*` endpoints; the repo holds no Bitkub API docs
  or fixtures to confirm against. Record a sanitized v3 fixture (v3 uses
  `btc_thb`, `/api/v3/market/*`, and signs timestamp + method + path +
  query/body), then migrate with a symbol normalizer before any live use.
  booktrading's Go client already has a v3 implementation to mirror
  (`backend/internal/adapter/exchange/bitkub/orders_v3.go`). Market-buy THB is derived from the
  current ask, so the filled base quantity can differ slightly; reconcile
  fills from the order history.
- Momentum and Thai-stock strategies size positions from a hard-coded
  balance (10k / 100k). Pass the real (or paper) balance in.
- `GridTradingStrategy.update_grid_after_fill` is never called, so grid
  levels never re-arm after a fill. It also cannot match anything as
  written: buy levels sit below the centre and sell levels above, so
  `filled * (1 ± spacing)` never lands on an opposite level. A level is also
  deactivated when its signal is skipped (e.g. a sell with no position).
  Redesign as buy/sell level pairs and re-arm only on a confirmed fill.
- Move money math to `Decimal` at the exchange boundary, with lot-size and
  tick-size rounding.
- Make `DatabaseManager` injectable instead of connecting in
  `TradingBot.__init__`.

### P2
- Clean up the ruff/pyupgrade backlog and widen the CI lint scope.
- Remove the unused `ta-lib`, `pandas-ta`, `alpaca` and `oanda` pins, or wire
  them up.

## Done in this pass (pass 4)
- Repeated-signal fix: `TradingBot` remembers the open time of the last bar
  it analysed per symbol (`_last_evaluated_bar`) and skips
  `strategy.analyze` until a newer closed bar arrives. Before, a 4h
  timeframe re-analysed the same closed bar every 60 s and could buy on
  every cycle. A failed kline refresh (same bars) is not re-traded either;
  tick-fallback symbols still analyse each new tick. Removed two unused
  imports in `bot.py`.
- Tests: `test_each_closed_bar_is_analysed_once` (fails without the fix)
  and `test_tick_fallback_is_analysed_every_cycle` in `tests/test_ohlcv.py`.
  Full suite 60 passed; CI ruff gate clean. Paper mode only.
- Exchange timestamps: Binance, Binance TH and Bitkub epoch-ms values go
  through `base_exchange.utc_from_ms` (naive UTC, the `utcnow()` convention
  of the paper exchange and database) instead of host-local
  `datetime.fromtimestamp`; Bitkub order stamps use `utc_now()`.
  `tests/test_utc_timestamps.py` (3 tests, run under TZ=Asia/Bangkok).
- Binance order mapping (`_order_result`): ccxt returns `fee: None` and
  `price: None` on market orders, so `order.get("fee", {}).get(...)` raised
  *after* a live order was placed (position never tracked) and the price
  was `None`. Now price = `average`, then `price`, then the reference price;
  fee falls back to the `fees` list; null `filled` becomes 0.
- NaN guards: `PaperExchange.place_order` and `TradingBot._execute_signal`
  reject NaN/inf amounts and prices (NaN passed `not x` and `x <= 0`, so one
  NaN ticker or size poisoned every paper balance). `_close_position` passes
  the position's price as reference and tolerates `fees=None`.
  `tests/test_nonfinite_and_ccxt_nulls.py`; suite 69 passed. Open: buy fees
  are not in the entry price, so realized PnL is overstated by the buy fee.

## Done in pass 3
- OHLCV P0: `BaseExchange.get_ohlcv()` (default `None`) with helpers
  `ohlcv_frame()` (parses ccxt rows and raw Binance klines, drops invalid,
  duplicate and out-of-order bars), `closed_bars()` and
  `timeframe_seconds()`. Binance uses ccxt `fetch_ohlcv`, Binance TH its
  public klines, and `PaperExchange` delegates market data to the wrapped
  connector. `TradingBot._update_market_data` loads closed bars (configurable
  `timeframe`, `ohlcv_limit`; invalid timeframe fails fast), falls back to
  ticks only for connectors without klines, and never mixes ticks into kline
  history after a failed refresh.
- `tests/test_ohlcv.py` (9 offline tests, network layer faked). Full suite:
  50 passed; CI ruff gate clean. Paper mode only; no credentials used. The
  leaked Neon password still needs a manual rotation (not doable here).
- Review fix: Bitkub `place_order` no longer returns `OrderResult.price=0`
  for market orders (live position/PnL used 0 as the entry). New
  `order_result_price()`: echoed `rat` when positive, else the limit price,
  else the ticker reference used to size the order (ask for buys, bid for
  sells, last as fallback). 8 offline tests with a faked network layer;
  full suite 58 passed, CI ruff gate clean.

## Done in pass 1
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

## Done in pass 2
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
