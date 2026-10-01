"""Configuration management for trading bots."""

import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def is_live_mode(value: Optional[str]) -> bool:
    """Return True only for an explicit ``live`` trading mode."""
    return (value or "").strip().lower() == "live"


class Config:
    """Configuration class for trading bots."""

    # Database Configuration
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Trading Configuration
    TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # paper or live
    # Real orders only when TRADING_MODE is exactly "live"; any other value
    # (unset, typo, "Paper") keeps every exchange in paper/sandbox mode.
    LIVE_TRADING = is_live_mode(TRADING_MODE)
    MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", 1000))
    RISK_PERCENTAGE = float(os.getenv("RISK_PERCENTAGE", 2))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Exchange API Keys
    EXCHANGE_CONFIGS = {
        "binance": {
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET_KEY"),
            "sandbox": not LIVE_TRADING,
        },
        "binance_th": {
            "apiKey": os.getenv("BINANCE_TH_API_KEY"),
            "secret": os.getenv("BINANCE_TH_SECRET_KEY"),
            "testMode": not LIVE_TRADING,
            "baseUrl": "https://api.binance.th",
        },
        "coinbase": {
            "apiKey": os.getenv("COINBASE_API_KEY"),
            "secret": os.getenv("COINBASE_SECRET_KEY"),
            "sandbox": not LIVE_TRADING,
        },
        "bybit": {
            "apiKey": os.getenv("BYBIT_API_KEY"),
            "secret": os.getenv("BYBIT_SECRET_KEY"),
            "testnet": not LIVE_TRADING,
        },
        "bitkub": {
            "apiKey": os.getenv("BITKUB_API_KEY"),
            "secret": os.getenv("BITKUB_SECRET_KEY"),
            "baseUrl": os.getenv("BITKUB_BASE_URL", "https://api.bitkub.com"),
        },
        "alpaca": {
            "key_id": os.getenv("ALPACA_API_KEY"),
            "secret_key": os.getenv("ALPACA_SECRET_KEY"),
            "base_url": os.getenv(
                "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
            ),
        },
        "oanda": {
            "access_token": os.getenv("OANDA_API_KEY"),
            "account_id": os.getenv("OANDA_ACCOUNT_ID"),
            "environment": os.getenv("OANDA_ENVIRONMENT", "practice"),
        },
        "innovestx": {
            "api_key": os.getenv("INNOVESTX_API_KEY"),
            "secret_key": os.getenv("INNOVESTX_SECRET_KEY"),
            "base_url": os.getenv(
                "INNOVESTX_BASE_URL", "https://api.innovestxonline.com"
            ),
            "environment": os.getenv("INNOVESTX_ENVIRONMENT", "sandbox"),
        },
    }

    @classmethod
    def get_exchange_config(cls, exchange_name: str) -> Dict[str, Any]:
        """Get configuration for a specific exchange."""
        return cls.EXCHANGE_CONFIGS.get(exchange_name, {})

    @classmethod
    def validate_config(cls) -> bool:
        """Validate that required configuration is present."""
        if not cls.DATABASE_URL:
            raise ValueError("DATABASE_URL configuration is required")
        return True
