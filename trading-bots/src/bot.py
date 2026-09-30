"""Main trading bot implementation."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from .config import Config
from .database import DatabaseManager
from .exchanges.base_exchange import BaseExchange, closed_bars, timeframe_seconds
from .exchanges.binance_exchange import BinanceExchange
from .exchanges.binance_th_exchange import BinanceThExchange
from .exchanges.bitkub_exchange import BitkubExchange
from .exchanges.innovestx_exchange import InnovestXExchange
from .exchanges.paper_exchange import PaperExchange
from .strategies.base_strategy import BaseStrategy, Position, Signal
from .strategies.grid_strategy import GridTradingStrategy
from .strategies.momentum_strategy import MomentumStrategy
from .strategies.thai_stock_strategy import ThaiStockStrategy


class TradingBot:
    """Main trading bot class that orchestrates strategy execution and trade management."""

    def __init__(self, bot_config: Dict[str, Any]):
        self.config_id = bot_config.get("id", str(uuid.uuid4()))
        self.bot_id = None  # Will be set during registration
        self.name = bot_config.get("name", f"Bot_{self.config_id[:8]}")
        self.platform = bot_config.get("platform")
        self.market = bot_config.get("market")
        self.strategy_name = bot_config.get("strategy", "grid")
        self.symbols = bot_config.get("symbols", [])
        self.config = bot_config.get("config", {})
        # Strategies analyse closed OHLCV bars of this timeframe.
        self.timeframe = self.config.get("timeframe", "1m")
        timeframe_seconds(self.timeframe)  # fail fast on an invalid timeframe
        self.ohlcv_limit = int(self.config.get("ohlcv_limit", 200))
        # Symbols whose history comes from exchange klines; ticks are never
        # mixed into those bars.
        self._ohlcv_symbols = set()
        # Open time of the last bar each symbol was analysed on. A closed bar
        # is analysed once: with a 60 s cycle and a long timeframe (e.g. 4h)
        # the same bar would otherwise emit the same signal every cycle.
        self._last_evaluated_bar: Dict[str, Any] = {}

        # Components
        self.db = DatabaseManager()
        self.exchange: Optional[BaseExchange] = None
        self.strategy: Optional[BaseStrategy] = None

        # State
        self.is_running = False
        self.last_update = datetime.now()
        self.performance_metrics = {
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": 0.0,
            "today_pnl": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
        }

    async def initialize(self) -> bool:
        """Initialize bot components."""
        try:
            # Initialize database
            await self.db.create_tables()

            # Register platform if not exists
            await self._register_platform()

            # Register this bot
            await self._register_bot()

            # Initialize exchange
            self.exchange = self._create_exchange()
            if not await self.exchange.connect():
                logger.error(f"Failed to connect to exchange for bot {self.name}")
                return False

            # Initialize strategy
            self.strategy = self._create_strategy()

            # Update bot status in database
            await self.db.update_bot_status(self.bot_id, "running")

            logger.info(f"Bot {self.name} initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize bot {self.name}: {e}")
            await self.db.update_bot_status(self.bot_id, "error")
            return False

    async def _register_platform(self):
        """Register the platform this bot uses."""
        platform_configs = {
            "binance": {
                "id": "binance",
                "name": "Binance",
                "available_markets": ["crypto"],
            },
            "binance_th": {
                "id": "binance_th",
                "name": "Binance TH",
                "available_markets": ["crypto"],
            },
            "coinbase": {
                "id": "coinbase",
                "name": "Coinbase Pro",
                "available_markets": ["crypto"],
            },
            "bybit": {"id": "bybit", "name": "Bybit", "available_markets": ["crypto"]},
            "bitkub": {
                "id": "bitkub",
                "name": "Bitkub",
                "available_markets": ["crypto"],
            },
            "alpaca": {
                "id": "alpaca",
                "name": "Alpaca",
                "available_markets": ["stock"],
            },
            "oanda": {"id": "oanda", "name": "OANDA", "available_markets": ["forex"]},
            "innovestx": {
                "id": "innovestx",
                "name": "InnovestX",
                "available_markets": ["stock"],
            },
            "interactive-brokers": {
                "id": "interactive-brokers",
                "name": "Interactive Brokers",
                "available_markets": ["stock", "forex"],
            },
            "td-ameritrade": {
                "id": "td-ameritrade",
                "name": "TD Ameritrade",
                "available_markets": ["stock"],
            },
            "kraken": {
                "id": "kraken",
                "name": "Kraken",
                "available_markets": ["crypto"],
            },
        }

        if self.platform in platform_configs:
            await self.db.register_platform(platform_configs[self.platform])

    async def _register_bot(self):
        """Register this bot in the database."""
        bot_data = {
            "config_id": self.config_id,
            "name": self.name,
            "platform": self.platform,
            "strategy": self.strategy_name,
            "symbol": ",".join(self.symbols) if self.symbols else "",
            "status": "stopped",
            "config": self.config,
            "pnl": self.performance_metrics["total_pnl"],
        }
        self.bot_id = await self.db.register_bot(bot_data)

    def _create_exchange(self) -> BaseExchange:
        """Create exchange connector based on platform.

        Unless ``TRADING_MODE=live`` is set explicitly, the connector is wrapped
        in ``PaperExchange`` so no order ever reaches a real account.
        """
        exchange_config = Config.get_exchange_config(self.platform)

        if self.platform == "binance":
            exchange = BinanceExchange(exchange_config)
        elif self.platform == "binance_th":
            exchange = BinanceThExchange(exchange_config)
        elif self.platform == "bitkub":
            exchange = BitkubExchange(exchange_config)
        elif self.platform == "innovestx":
            exchange = InnovestXExchange(exchange_config)
        # Add other exchanges here
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")

        if not Config.LIVE_TRADING:
            logger.info(f"Bot {self.name}: paper mode, orders are simulated")
            return PaperExchange(exchange)
        logger.warning(f"Bot {self.name}: LIVE trading on {self.platform}")
        return exchange

    def _create_strategy(self) -> BaseStrategy:
        """Create trading strategy based on configuration."""
        if self.strategy_name == "grid":
            return GridTradingStrategy(self.config)
        elif self.strategy_name == "momentum":
            return MomentumStrategy(self.config)
        elif self.strategy_name == "thai_stock":
            return ThaiStockStrategy(self.config)
        else:
            raise ValueError(f"Unsupported strategy: {self.strategy_name}")

    async def run(self):
        """Main bot execution loop."""
        self.is_running = True
        logger.info(f"Starting bot {self.name}")

        try:
            while self.is_running:
                await self._execute_trading_cycle()
                await asyncio.sleep(60)  # Wait 1 minute between cycles

        except Exception as e:
            logger.error(f"Error in bot {self.name} execution: {e}")
            await self.db.update_bot_status(self.bot_id, "error")
        finally:
            await self.stop()

    async def _execute_trading_cycle(self):
        """Execute one trading cycle."""
        try:
            # Update market data for all symbols
            for symbol in self.symbols:
                await self._update_market_data(symbol)

            # Check existing positions
            await self._manage_positions()

            # Generate new signals, once per new bar
            for symbol in self.symbols:
                bar = self._latest_bar(symbol)
                if bar is not None and self._last_evaluated_bar.get(symbol) == bar:
                    continue
                signal = await self.strategy.analyze(symbol)
                if bar is not None:
                    self._last_evaluated_bar[symbol] = bar
                if signal.action in ["buy", "sell"]:
                    await self._execute_signal(signal)

            # Update performance metrics
            await self._update_performance_metrics()

            self.last_update = datetime.now()

        except Exception as e:
            logger.error(f"Error in trading cycle for bot {self.name}: {e}")

    def _latest_bar(self, symbol: str):
        """Open time of the newest bar in the strategy history, or None."""
        df = self.strategy.historical_data.get(symbol)
        if df is None or df.empty or "timestamp" not in df.columns:
            return None
        return df["timestamp"].iloc[-1]

    async def _update_market_data(self, symbol: str):
        """Refresh the strategy's history with closed OHLCV bars.

        Real klines are preferred: indicators need true open/high/low/close
        bars, not one tick sampled per cycle. Connectors without klines fall
        back to accumulating observed ticks. Once a symbol has kline history,
        a failed refresh keeps the last good bars instead of appending ticks.
        """
        try:
            if await self._update_from_ohlcv(symbol):
                return
            if symbol in self._ohlcv_symbols:
                return

            ticker = await self.exchange.get_ticker(symbol)
            current_time = datetime.now()

            new_row = pd.DataFrame(
                {
                    "timestamp": [current_time],
                    "open": [ticker.last],
                    "high": [ticker.last],
                    "low": [ticker.last],
                    "close": [ticker.last],
                    "volume": [ticker.volume],
                }
            )

            # Only real observed ticks are used. Strategies wait until enough
            # history has accumulated instead of trading on fabricated bars.
            if symbol not in self.strategy.historical_data:
                df = new_row
            else:
                df = pd.concat(
                    [self.strategy.historical_data[symbol], new_row], ignore_index=True
                )
                df = df.tail(1000)  # Keep last 1000 data points

            self.strategy.update_historical_data(symbol, df)

        except Exception as e:
            logger.error(f"Failed to update market data for {symbol}: {e}")

    async def _update_from_ohlcv(self, symbol: str) -> bool:
        """Load closed klines into the strategy; True when history was set."""
        try:
            bars = await self.exchange.get_ohlcv(
                symbol, timeframe=self.timeframe, limit=self.ohlcv_limit
            )
        except Exception as e:
            logger.warning(f"OHLCV fetch failed for {symbol}: {e}")
            return False
        if bars is None:
            return False
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        bars = closed_bars(bars, self.timeframe, now)
        if bars.empty:
            return False
        self._ohlcv_symbols.add(symbol)
        self.strategy.update_historical_data(symbol, bars)
        return True

    async def _manage_positions(self):
        """Manage existing positions."""
        # Iterate over a snapshot: closing a position mutates the dict.
        for symbol, position in list(self.strategy.positions.items()):
            try:
                # Get current price
                ticker = await self.exchange.get_ticker(symbol)
                current_price = ticker.last

                # Update position with current price
                self.strategy.update_position_price(symbol, current_price)

                # Check if position should be closed
                if await self.strategy.should_exit(position, current_price):
                    await self._close_position(position)

            except Exception as e:
                logger.error(f"Error managing position for {symbol}: {e}")

    async def _execute_signal(self, signal: Signal):
        """Execute a trading signal."""
        try:
            logger.info(
                f"Executing {signal.action} signal for {signal.symbol} at ${signal.price:.4f}"
            )

            if not signal.amount or signal.amount <= 0 or not signal.price or signal.price <= 0:
                logger.warning(f"Skipping {signal.action} for {signal.symbol}: invalid amount/price")
                return

            held = self.strategy.positions.get(signal.symbol)
            amount = signal.amount
            if signal.action == "sell":
                # Spot, long-only: never sell inventory the bot does not hold.
                if held is None or held.amount <= 0:
                    logger.info(f"Skipping sell for {signal.symbol}: no open position")
                    return
                amount = min(amount, held.amount)

            # Execute the order
            order_result = await self.exchange.place_order(
                symbol=signal.symbol,
                side=signal.action,
                amount=amount,
                price=signal.price,
                order_type="market",
            )

            realized_pnl = 0.0
            if signal.action == "sell":
                realized_pnl = (
                    (order_result.price - held.entry_price) * order_result.amount
                    - (order_result.fees or 0.0)
                )

            # Record trade in database
            trade_data = {
                "id": str(uuid.uuid4()),
                "bot_id": self.bot_id,
                "symbol": signal.symbol,
                "side": signal.action,
                "amount": order_result.amount,
                "price": order_result.price,
                "pnl": realized_pnl,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self.db.insert_trade(trade_data)

            # Update strategy position tracking (one aggregated long per symbol)
            if signal.action == "buy":
                if held is not None and held.amount > 0:
                    total = held.amount + order_result.amount
                    held.entry_price = (
                        held.entry_price * held.amount
                        + order_result.price * order_result.amount
                    ) / total
                    held.amount = total
                    held.current_price = order_result.price
                else:
                    self.strategy.add_position(
                        Position(
                            symbol=signal.symbol,
                            side="long",
                            amount=order_result.amount,
                            entry_price=order_result.price,
                            current_price=order_result.price,
                            pnl=0.0,
                            timestamp=datetime.now(),
                        )
                    )
            else:
                held.amount -= order_result.amount
                if held.amount <= 1e-12:
                    self.strategy.remove_position(signal.symbol)
                self.performance_metrics["total_pnl"] += realized_pnl
                self.performance_metrics["today_pnl"] += realized_pnl
                if realized_pnl > 0:
                    self.performance_metrics["winning_trades"] += 1

            # Update performance metrics
            self.performance_metrics["total_trades"] += 1

            logger.info(
                f"Successfully executed {signal.action} order for {signal.symbol}"
            )

        except Exception as e:
            logger.error(f"Failed to execute signal for {signal.symbol}: {e}")

    async def _close_position(self, position: Position):
        """Close an existing position."""
        try:
            # Determine opposite side
            close_side = "sell" if position.side == "long" else "buy"

            # Execute closing order
            order_result = await self.exchange.place_order(
                symbol=position.symbol,
                side=close_side,
                amount=position.amount,
                order_type="market",
            )

            # Calculate P&L
            if position.side == "long":
                pnl = (order_result.price - position.entry_price) * position.amount
            else:
                pnl = (position.entry_price - order_result.price) * position.amount

            pnl -= order_result.fees  # Subtract fees

            # Record closing trade
            trade_data = {
                "id": str(uuid.uuid4()),
                "bot_id": self.bot_id,
                "symbol": position.symbol,
                "side": close_side,
                "amount": order_result.amount,
                "price": order_result.price,
                "pnl": pnl,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self.db.insert_trade(trade_data)

            # Update performance metrics and database
            self.performance_metrics["total_trades"] += 1
            self.performance_metrics["total_pnl"] += pnl
            self.performance_metrics["today_pnl"] += pnl

            if pnl > 0:
                self.performance_metrics["winning_trades"] += 1

            # Remove position from tracking
            self.strategy.remove_position(position.symbol)

            # Update statistics in database
            await self._update_performance_metrics()

            logger.info(f"Closed position for {position.symbol} with P&L: ${pnl:.2f}")

        except Exception as e:
            logger.error(f"Failed to close position for {position.symbol}: {e}")

    async def _update_performance_metrics(self):
        """Update bot performance metrics in database."""
        try:
            # Calculate win rate
            if self.performance_metrics["total_trades"] > 0:
                win_rate = (
                    self.performance_metrics["winning_trades"]
                    / self.performance_metrics["total_trades"]
                ) * 100
            else:
                win_rate = 0.0

            # Update bot status with current metrics
            await self.db.update_bot_status(
                self.bot_id,
                "running",
                self.performance_metrics["total_pnl"],
                self.performance_metrics["today_pnl"],
            )

            # Insert detailed metrics
            await self.db.insert_bot_metrics(
                self.bot_id,
                {
                    "balance": 10000.0,  # Placeholder - would get from exchange
                    "pnl": self.performance_metrics["total_pnl"],
                    "drawdown": self.performance_metrics["max_drawdown"],
                    "sharpe_ratio": self.performance_metrics["sharpe_ratio"],
                    "win_rate": win_rate,
                    "total_trades": self.performance_metrics["total_trades"],
                },
            )

        except Exception as e:
            logger.error(f"Failed to update performance metrics: {e}")

    async def stop(self):
        """Stop the trading bot."""
        self.is_running = False

        if self.exchange:
            await self.exchange.disconnect()

        await self.db.update_bot_status(self.bot_id, "stopped")
        logger.info(f"Bot {self.name} stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        return {
            "id": self.bot_id,
            "name": self.name,
            "platform": self.platform,
            "market": self.market,
            "strategy": self.strategy_name,
            "status": "running" if self.is_running else "stopped",
            "symbols": self.symbols,
            "last_update": self.last_update.isoformat(),
            "performance": self.performance_metrics,
            "positions": len(self.strategy.positions) if self.strategy else 0,
        }
