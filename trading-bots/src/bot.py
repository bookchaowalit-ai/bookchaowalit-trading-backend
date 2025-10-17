"""Main trading bot implementation."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from .config import Config
from .database import DatabaseManager
from .exchanges.base_exchange import BaseExchange
from .exchanges.binance_exchange import BinanceExchange
from .exchanges.binance_th_exchange import BinanceThExchange
from .exchanges.bitkub_exchange import BitkubExchange
from .exchanges.innovestx_exchange import InnovestXExchange
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
        """Create exchange connector based on platform."""
        exchange_config = Config.get_exchange_config(self.platform)

        if self.platform == "binance":
            return BinanceExchange(exchange_config)
        elif self.platform == "binance_th":
            return BinanceThExchange(exchange_config)
        elif self.platform == "bitkub":
            return BitkubExchange(exchange_config)
        elif self.platform == "innovestx":
            return InnovestXExchange(exchange_config)
        # Add other exchanges here
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")

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

            # Generate new signals
            for symbol in self.symbols:
                signal = await self.strategy.analyze(symbol)
                if signal.action in ["buy", "sell"]:
                    await self._execute_signal(signal)

            # Update performance metrics
            await self._update_performance_metrics()

            self.last_update = datetime.now()

        except Exception as e:
            logger.error(f"Error in trading cycle for bot {self.name}: {e}")

    async def _update_market_data(self, symbol: str):
        """Update historical market data for analysis."""
        try:
            # Get recent price data (this would typically fetch from exchange)
            # For now, we'll simulate with ticker data
            ticker = await self.exchange.get_ticker(symbol)

            # In a real implementation, you'd fetch OHLCV data
            # Here we'll create a simple data point
            current_time = datetime.now()

            # Create or update DataFrame
            if symbol not in self.strategy.historical_data:
                # Initialize with some dummy data for demonstration
                dates = pd.date_range(end=current_time, periods=100, freq="1H")
                base_price = ticker.last

                # Generate realistic OHLCV data
                np_random = pd.np.random
                price_changes = np_random.normal(0, 0.02, 100)  # 2% volatility
                prices = [base_price]

                for change in price_changes[1:]:
                    prices.append(prices[-1] * (1 + change))

                df = pd.DataFrame(
                    {
                        "timestamp": dates,
                        "open": prices,
                        "high": [
                            p * (1 + abs(np_random.normal(0, 0.01))) for p in prices
                        ],
                        "low": [
                            p * (1 - abs(np_random.normal(0, 0.01))) for p in prices
                        ],
                        "close": prices,
                        "volume": np_random.uniform(1000, 10000, 100),
                    }
                )

                self.strategy.update_historical_data(symbol, df)
            else:
                # Update existing data with new tick
                df = self.strategy.historical_data[symbol].copy()
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

                df = pd.concat([df, new_row], ignore_index=True)
                df = df.tail(1000)  # Keep last 1000 data points

                self.strategy.update_historical_data(symbol, df)

        except Exception as e:
            logger.error(f"Failed to update market data for {symbol}: {e}")

    async def _manage_positions(self):
        """Manage existing positions."""
        for symbol, position in self.strategy.positions.items():
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

            # Check balance before trading
            balance = await self.exchange.get_balance()

            # Execute the order
            order_result = await self.exchange.place_order(
                symbol=signal.symbol,
                side=signal.action,
                amount=signal.amount,
                price=signal.price,
                order_type="market",
            )

            # Record trade in database
            trade_data = {
                "id": str(uuid.uuid4()),
                "bot_id": self.bot_id,
                "symbol": signal.symbol,
                "side": signal.action,
                "amount": order_result.amount,
                "price": order_result.price,
                "pnl": 0.0,  # Will be calculated later
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self.db.insert_trade(trade_data)

            # Update strategy position tracking
            if signal.action == "buy":
                position = Position(
                    symbol=signal.symbol,
                    side="long",
                    amount=order_result.amount,
                    entry_price=order_result.price,
                    current_price=order_result.price,
                    pnl=0.0,
                    timestamp=datetime.now(),
                )
                self.strategy.add_position(position)

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
