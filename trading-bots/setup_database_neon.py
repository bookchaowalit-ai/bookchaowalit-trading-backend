#!/usr/bin/env python3
"""
Setup script to initialize PostgreSQL database tables for trading bots.
This script creates the required tables and sets up the database schema.
"""

import os
import sys
from datetime import datetime

import psycopg2

# Add the src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
from src.config import Config

# Load environment variables
load_dotenv()

# SQL to create all required tables
CREATE_TABLES_SQL = """
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_trades_bot_id ON trades(bot_id);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_bots_platform ON bots(platform);
CREATE INDEX IF NOT EXISTS idx_bots_status ON bots(status);
CREATE INDEX IF NOT EXISTS idx_bot_metrics_bot_id ON bot_metrics(bot_id);
CREATE INDEX IF NOT EXISTS idx_bot_metrics_timestamp ON bot_metrics(timestamp);
"""

# Platform configurations
PLATFORMS = [
    {
        "name": "binance",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "binance_th",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "coinbase",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "bybit",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "bitkub",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "kraken",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "alpaca",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "oanda",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
    {
        "name": "innovestx",
        "status": "active",
        "total_bots": 0,
        "active_bots": 0,
        "total_balance": 0,
    },
]


def setup_database():
    """Initialize the database tables and insert platform data."""
    try:
        print("🔧 Setting up PostgreSQL database...")

        if not Config.DATABASE_URL:
            raise ValueError("DATABASE_URL is required")

        print(f"📡 Connecting to database...")

        # Connect to database
        conn = psycopg2.connect(Config.DATABASE_URL)

        print("✓ Connected to PostgreSQL database")

        # Create tables
        print("📋 Creating database tables...")
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLES_SQL)
            conn.commit()

        print("✓ Database tables created successfully")

        # Insert platform data
        print("🏢 Registering platforms...")
        success_count = 0

        for platform in PLATFORMS:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO platforms (name, status, total_bots, active_bots, total_balance, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (name) DO UPDATE SET
                            status = EXCLUDED.status,
                            updated_at = EXCLUDED.updated_at
                    """,
                        (
                            platform["name"],
                            platform["status"],
                            platform["total_bots"],
                            platform["active_bots"],
                            platform["total_balance"],
                            datetime.utcnow(),
                        ),
                    )
                    conn.commit()

                print(f"✓ Registered platform: {platform['name']}")
                success_count += 1

            except Exception as e:
                print(f"✗ Error registering {platform['name']}: {e}")

        print(f"\nSuccessfully registered {success_count}/{len(PLATFORMS)} platforms")

        if success_count == len(PLATFORMS):
            print("\n🎉 Database setup completed successfully!")
            print(
                "Your trading bots can now register themselves and the trading-monitor will be able to read the data."
            )
        else:
            print(
                f"\n⚠️  {len(PLATFORMS) - success_count} platform(s) failed to register."
            )

        conn.close()
        return success_count == len(PLATFORMS)

    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False


def verify_setup():
    """Verify the setup by checking if platforms exist in the database."""
    try:
        print("\n🔍 Verifying database setup...")

        conn = psycopg2.connect(Config.DATABASE_URL)

        with conn.cursor() as cursor:
            cursor.execute("SELECT name, status FROM platforms ORDER BY name")
            platforms = cursor.fetchall()

        if platforms:
            print(f"\n📊 Found {len(platforms)} platforms in database:")
            for platform in platforms:
                status_emoji = "✅" if platform[1] == "active" else "⏸️"
                print(f"  {status_emoji} {platform[0]} ({platform[1]})")
        else:
            print("❌ No platforms found in database")

        conn.close()
        return len(platforms) > 0

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Starting database setup for trading bot system...")
    print("=" * 50)

    if setup_database():
        if verify_setup():
            print("\n✅ Database setup and verification completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Database verification failed!")
            sys.exit(1)
    else:
        print("\n❌ Database setup failed!")
        sys.exit(1)
