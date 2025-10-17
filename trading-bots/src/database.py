"""Database operations for trading bots."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from loguru import logger
from psycopg2.extras import RealDictCursor

from .config import Config


class DatabaseManager:
    """Manages database operations for trading bots."""

    def __init__(self):
        self.connection: Optional[psycopg2.extensions.connection] = None
        self._connect()

    def _connect(self) -> None:
        """Connect to PostgreSQL database."""
        try:
            if not Config.DATABASE_URL:
                raise ValueError("DATABASE_URL is required")

            self.connection = psycopg2.connect(
                Config.DATABASE_URL, cursor_factory=RealDictCursor
            )
            logger.info("Connected to PostgreSQL database")

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def create_tables(self) -> None:
        """Create database tables if they don't exist."""
        try:
            tables_sql = """
            -- Platforms table
            CREATE TABLE IF NOT EXISTS platforms (
                name VARCHAR(255) PRIMARY KEY,
                status VARCHAR(50) DEFAULT 'unknown',
                last_ping TIMESTAMP,
                total_bots INTEGER DEFAULT 0,
                active_bots INTEGER DEFAULT 0,
                total_balance DECIMAL(15,2) DEFAULT 0,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Bots table
            CREATE TABLE IF NOT EXISTS bots (
                id UUID PRIMARY KEY,
                config_id VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                platform VARCHAR(255) REFERENCES platforms(name),
                strategy VARCHAR(255),
                symbol VARCHAR(100),
                status VARCHAR(50) DEFAULT 'inactive',
                config JSONB DEFAULT '{}',
                balance DECIMAL(15,2) DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                total_pnl DECIMAL(15,2) DEFAULT 0,
                last_trade TIMESTAMP,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Trades table
            CREATE TABLE IF NOT EXISTS trades (
                id UUID PRIMARY KEY,
                bot_id UUID REFERENCES bots(id),
                platform VARCHAR(255) REFERENCES platforms(name),
                symbol VARCHAR(100) NOT NULL,
                side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
                quantity DECIMAL(20,8) NOT NULL,
                price DECIMAL(20,8) NOT NULL,
                fees DECIMAL(20,8) DEFAULT 0,
                status VARCHAR(50) DEFAULT 'pending',
                trade_type VARCHAR(50) DEFAULT 'market',
                timestamp TIMESTAMP NOT NULL,
                metadata JSONB DEFAULT '{}',
                pnl DECIMAL(15,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Bot metrics table
            CREATE TABLE IF NOT EXISTS bot_metrics (
                id UUID PRIMARY KEY,
                bot_id UUID REFERENCES bots(id),
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl DECIMAL(15,2) DEFAULT 0,
                win_rate DECIMAL(5,2) DEFAULT 0,
                sharpe_ratio DECIMAL(10,4) DEFAULT 0,
                max_drawdown DECIMAL(5,2) DEFAULT 0,
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """

            with self.connection.cursor() as cursor:
                cursor.execute(tables_sql)
                self.connection.commit()

            logger.info("Database tables created successfully")

        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"Error creating tables: {e}")
            raise

    def insert_trade(self, trade_data: Dict[str, Any]) -> str:
        """Insert a new trade record."""
        try:
            trade_id = str(uuid.uuid4())

            # Format the trade data
            formatted_trade = {
                "id": trade_id,
                "bot_id": trade_data.get("bot_id"),
                "platform": trade_data.get("platform"),
                "symbol": trade_data.get("symbol"),
                "side": trade_data.get("side"),
                "quantity": float(trade_data.get("quantity", 0)),
                "price": float(trade_data.get("price", 0)),
                "fees": float(trade_data.get("fees", 0)),
                "status": trade_data.get("status", "pending"),
                "trade_type": trade_data.get("trade_type", "market"),
                "timestamp": trade_data.get("timestamp", datetime.utcnow().isoformat()),
                "metadata": json.dumps(trade_data.get("metadata", {})),
                "pnl": float(trade_data.get("pnl", 0)),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO trades (
                        id, bot_id, platform, symbol, side, quantity, price, fees,
                        status, trade_type, timestamp, metadata, pnl, created_at, updated_at
                    ) VALUES (
                        %(id)s, %(bot_id)s, %(platform)s, %(symbol)s, %(side)s, %(quantity)s,
                        %(price)s, %(fees)s, %(status)s, %(trade_type)s, %(timestamp)s,
                        %(metadata)s, %(pnl)s, %(created_at)s, %(updated_at)s
                    )
                """,
                    formatted_trade,
                )
                self.connection.commit()

            logger.info(f"Trade inserted successfully with ID: {trade_id}")
            return trade_id

        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"Error inserting trade: {e}")
            raise

    async def update_bot_status(
        self, bot_id: str, status: str, error_message: str = None
    ) -> None:
        """Update bot status."""
        try:
            query = "UPDATE bots SET status = %s, updated_at = %s"
            params = [status, datetime.utcnow().isoformat()]

            if error_message:
                query += ", last_error = %s"
                params.append(error_message)

            query += " WHERE id = %s"
            params.append(bot_id)

            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                self.connection.commit()

            logger.info(f"Bot {bot_id} status updated to {status}")

        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"Error updating bot status: {e}")
            raise

    async def insert_bot_metrics(self, bot_id: str, metrics: dict) -> None:
        """Insert bot performance metrics."""
        try:
            metric_id = str(uuid.uuid4())
            query = """
                INSERT INTO bot_metrics (
                    id, bot_id, total_trades, winning_trades, losing_trades,
                    total_pnl, win_rate, sharpe_ratio, max_drawdown,
                    timestamp, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            with self.connection.cursor() as cursor:
                cursor.execute(
                    query,
                    [
                        metric_id,
                        bot_id,
                        metrics.get("total_trades", 0),
                        metrics.get("winning_trades", 0),
                        metrics.get("losing_trades", 0),
                        metrics.get("pnl", 0.0),  # total_pnl
                        metrics.get("win_rate", 0.0),
                        metrics.get("sharpe_ratio", 0.0),
                        metrics.get("drawdown", 0.0),  # max_drawdown
                        datetime.utcnow().isoformat(),  # timestamp
                        datetime.utcnow().isoformat(),  # created_at
                        datetime.utcnow().isoformat(),  # updated_at
                    ],
                )
                self.connection.commit()

            logger.info(f"Bot metrics inserted for {bot_id}")

        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"Error inserting bot metrics: {e}")
            # Don't raise - metrics insertion should not fail the bot

    def get_bot_config(self, bot_id: str) -> Optional[Dict[str, Any]]:
        """Get bot configuration."""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM bots WHERE id = %s", (bot_id,))
                result = cursor.fetchone()

            if result:
                logger.info(f"Retrieved config for bot {bot_id}")
                return dict(result)
            else:
                logger.warning(f"Bot {bot_id} not found")
                return None

        except Exception as e:
            logger.error(f"Error retrieving bot config: {e}")
            raise

    def save_bot_config(self, bot_config: Dict[str, Any]) -> str:
        """Save or update bot configuration."""
        try:
            bot_id = bot_config.get("id") or str(uuid.uuid4())

            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO bots (
                        id, name, platform, strategy, symbol, status, config,
                        balance, total_trades, total_pnl, last_trade, last_error,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        platform = EXCLUDED.platform,
                        strategy = EXCLUDED.strategy,
                        symbol = EXCLUDED.symbol,
                        status = EXCLUDED.status,
                        config = EXCLUDED.config,
                        balance = EXCLUDED.balance,
                        total_trades = EXCLUDED.total_trades,
                        total_pnl = EXCLUDED.total_pnl,
                        last_trade = EXCLUDED.last_trade,
                        last_error = EXCLUDED.last_error,
                        updated_at = EXCLUDED.updated_at
                """,
                    (
                        bot_id,
                        bot_config.get("name"),
                        bot_config.get("platform"),
                        bot_config.get("strategy"),
                        bot_config.get("symbol"),
                        bot_config.get("status", "inactive"),
                        json.dumps(bot_config.get("config", {})),
                        float(bot_config.get("balance", 0)),
                        bot_config.get("total_trades", 0),
                        float(bot_config.get("total_pnl", 0)),
                        bot_config.get("last_trade"),
                        bot_config.get("last_error"),
                        bot_config.get("created_at", datetime.utcnow().isoformat()),
                        datetime.utcnow().isoformat(),
                    ),
                )
                self.connection.commit()

            logger.info(f"Bot config saved with ID: {bot_id}")
            return bot_id

        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"Error saving bot config: {e}")
            raise

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    async def register_platform(self, platform_config: Dict[str, Any]) -> None:
        """Register a platform if it doesn't exist."""
        try:
            platform_name = platform_config.get("id")

            with self.connection.cursor() as cursor:
                # Check if platform exists
                cursor.execute(
                    "SELECT name FROM platforms WHERE name = %s", (platform_name,)
                )
                if cursor.fetchone():
                    logger.debug(f"Platform {platform_name} already exists")
                    return

                # Insert new platform
                cursor.execute(
                    """
                    INSERT INTO platforms (name, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                """,
                    (
                        platform_name,
                        "active",
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                    ),
                )

                self.connection.commit()
                logger.info(f"Platform {platform_name} registered successfully")

        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"Error registering platform: {e}")
            raise

    async def register_bot(self, bot_data: Dict[str, Any]) -> str:
        """Register a bot in the database."""
        try:
            # Generate UUID for database ID
            db_bot_id = str(uuid.uuid4())

            with self.connection.cursor() as cursor:
                # Check if bot with this config ID already exists
                config_id = bot_data.get("config_id", bot_data.get("id"))
                cursor.execute("SELECT id FROM bots WHERE config_id = %s", (config_id,))
                existing_bot = cursor.fetchone()

                if existing_bot:
                    logger.debug(
                        f"Bot {config_id} already exists with ID {existing_bot['id']}"
                    )
                    return existing_bot["id"]

                # Insert new bot
                cursor.execute(
                    """
                    INSERT INTO bots (
                        id, config_id, name, platform, strategy, symbol, status,
                        config, balance, total_trades, total_pnl, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """,
                    (
                        db_bot_id,
                        config_id,
                        bot_data.get("name"),
                        bot_data.get("platform_id", bot_data.get("platform")),
                        bot_data.get("strategy"),
                        bot_data.get("symbol"),
                        bot_data.get("status", "inactive"),
                        json.dumps(bot_data.get("config", {})),
                        float(bot_data.get("balance", 0)),
                        int(bot_data.get("total_trades", 0)),
                        float(bot_data.get("pnl", 0)),
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                    ),
                )

                self.connection.commit()
                logger.info(f"Bot {config_id} registered with ID {db_bot_id}")
                return db_bot_id

        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"Error registering bot: {e}")
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
