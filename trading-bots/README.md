# Trading Bots System

A Python-based automated trading system that supports multiple exchanges, markets (crypto, stock, forex), and trading strategies. The system stores all trading data in Supabase or Neon databases for monitoring through the web dashboard.

## Features

- **Multi-Exchange Support**: Binance, Coinbase, Alpaca, OANDA, and more
- **Multiple Markets**: Cryptocurrency, Stock, and Forex trading
- **Trading Strategies**: Grid trading, Momentum trading, and extensible framework
- **Database Integration**: Supabase and Neon PostgreSQL support
- **Risk Management**: Position sizing, stop-loss, take-profit
- **Real-time Monitoring**: Performance metrics and trade tracking
- **Paper Trading**: Test strategies without real money

## Project Structure

```
trading-bots/
├── src/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── database.py            # Database operations
│   ├── bot.py                 # Main trading bot class
│   ├── bot_manager.py         # Multi-bot orchestration
│   ├── exchanges/             # Exchange connectors
│   │   ├── __init__.py
│   │   ├── base_exchange.py   # Abstract exchange interface
│   │   └── binance_exchange.py # Binance implementation
│   └── strategies/            # Trading strategies
│       ├── __init__.py
│       ├── base_strategy.py   # Abstract strategy interface
│       ├── grid_strategy.py   # Grid trading strategy
│       └── momentum_strategy.py # Momentum trading strategy
├── main.py                    # Entry point
├── bot_configs.json          # Bot configurations
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variables template
└── README.md               # This file
```

## Installation

### Prerequisites

- Python 3.8+
- Supabase account OR Neon database
- Exchange API keys (for live trading)

### Setup

1. **Clone and navigate to the trading-bots directory:**
```bash
cd trading-bots
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your API keys and database credentials
```

5. **Setup database tables:**
The system will automatically create tables on first run, or you can create them manually:

```sql
-- Platforms table
CREATE TABLE platforms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    available_markets TEXT[] NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'error')),
    total_bots INTEGER DEFAULT 0,
    active_bots INTEGER DEFAULT 0,
    total_pnl DECIMAL(10,2) DEFAULT 0,
    today_pnl DECIMAL(10,2) DEFAULT 0,
    market_stats JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Bots table
CREATE TABLE bots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    platform TEXT REFERENCES platforms(id),
    market TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'stopped', 'error')),
    strategy TEXT NOT NULL,
    config JSONB DEFAULT '{}',
    pnl DECIMAL(10,2) DEFAULT 0,
    today_pnl DECIMAL(10,2) DEFAULT 0,
    trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2) DEFAULT 0,
    last_trade TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Trades table
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    bot_id TEXT REFERENCES bots(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    amount DECIMAL(18,8) NOT NULL,
    price DECIMAL(18,8) NOT NULL,
    pnl DECIMAL(10,2) DEFAULT 0,
    fees DECIMAL(10,2) DEFAULT 0,
    timestamp TIMESTAMP DEFAULT NOW(),
    exchange_order_id TEXT,
    metadata JSONB DEFAULT '{}'
);

-- Bot performance metrics
CREATE TABLE bot_metrics (
    id SERIAL PRIMARY KEY,
    bot_id TEXT REFERENCES bots(id),
    timestamp TIMESTAMP DEFAULT NOW(),
    balance DECIMAL(18,8),
    pnl DECIMAL(10,2),
    drawdown DECIMAL(5,2),
    sharpe_ratio DECIMAL(8,4),
    win_rate DECIMAL(5,2),
    total_trades INTEGER
);
```

## Configuration

### Environment Variables (.env)

```env
# Database Configuration
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here

# Exchange API Keys
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key

# InnovestX (Thai Stock Market)
INNOVESTX_API_KEY=your_innovestx_api_key
INNOVESTX_SECRET_KEY=your_innovestx_secret_key

# Trading Configuration
TRADING_MODE=paper  # paper or live
MAX_POSITION_SIZE=1000
RISK_PERCENTAGE=2
LOG_LEVEL=INFO
```

### Bot Configuration (bot_configs.json)

```json
[
  {
    "id": "btc_grid_bot",
    "name": "BTC Grid Bot",
    "platform": "binance",
    "market": "crypto",
    "strategy": "grid",
    "symbols": ["BTC/USDT"],
    "config": {
      "grid_levels": 10,
      "grid_spacing": 0.01,
      "base_order_size": 100,
      "max_position_size": 1000,
      "risk_per_trade": 0.02
    }
  }
]
```

## Usage

### Start All Bots

```bash
python main.py
```

### Start Specific Bot

```python
from src.bot_manager import BotManager
import asyncio

async def start_single_bot():
    manager = BotManager()
    
    bot_config = {
        "id": "my_bot",
        "name": "My Trading Bot",
        "platform": "binance",
        "market": "crypto",
        "strategy": "grid",
        "symbols": ["BTC/USDT"],
        "config": {"grid_levels": 10}
    }
    
    await manager.start_bot(bot_config)

asyncio.run(start_single_bot())
```

## Trading Strategies

**Market data (all strategies):** each cycle the bot loads closed OHLCV bars
from the exchange (Binance via ccxt `fetch_ohlcv`, Binance TH via the public
klines endpoint; the still-forming bar is dropped). Connectors without klines
(Bitkub, InnovestX) fall back to one observed tick per cycle.
- `timeframe`: bar size such as `1m`, `5m`, `1h` (default: `1m`)
- `ohlcv_limit`: number of bars requested per refresh (default: 200)

### Grid Trading Strategy

Places buy and sell orders at regular intervals around the current price to profit from market volatility.

**Configuration:**
- `grid_levels`: Number of grid levels (default: 10)
- `grid_spacing`: Spacing between levels as percentage (default: 0.01 = 1%)
- `base_order_size`: Base order size in quote currency

### Momentum Strategy

Identifies trends using technical indicators (RSI, Moving Averages) and trades in the direction of strong price movements.

**Configuration:**
- `rsi_period`: RSI calculation period (default: 14)
- `ma_short`: Short moving average period (default: 10)
- `ma_long`: Long moving average period (default: 30)
- `rsi_oversold`: RSI oversold threshold (default: 30)
- `rsi_overbought`: RSI overbought threshold (default: 70)

## Supported Exchanges

### Cryptocurrency
- **Binance**: Spot and futures trading
- **Coinbase Pro**: Spot trading
- **Bybit**: Spot and derivatives

### Stock Trading
- **Alpaca**: US stocks and ETFs
- **Interactive Brokers**: Global stocks
- **InnovestX**: Thai stock market (SET)

### Forex Trading
- **OANDA**: Major and minor currency pairs
- **Interactive Brokers**: Forex pairs

## Risk Management

- **Position Sizing**: Automatic calculation based on account balance and risk percentage
- **Stop Loss**: Configurable stop-loss levels
- **Take Profit**: Configurable profit targets
- **Maximum Position Size**: Hard limits on position sizes
- **Drawdown Protection**: Automatic bot shutdown on excessive losses

## Monitoring and Logging

- **Real-time Logs**: Structured logging with different levels
- **Performance Metrics**: P&L, win rate, Sharpe ratio, drawdown
- **Database Storage**: All trades and metrics stored for analysis
- **Web Dashboard**: Monitor through the Next.js dashboard

## Development

### Adding New Exchange

1. Create new exchange class inheriting from `BaseExchange`
2. Implement all abstract methods
3. Add exchange configuration to `Config.EXCHANGE_CONFIGS`
4. Update bot creation logic in `TradingBot._create_exchange()`

### Adding New Strategy

1. Create new strategy class inheriting from `BaseStrategy`
2. Implement `analyze()`, `should_exit()`, and `get_position_size()` methods
3. Add strategy creation logic in `TradingBot._create_strategy()`

### Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

## Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "main.py"]
```

### Systemd Service

```ini
[Unit]
Description=Trading Bots System
After=network.target

[Service]
Type=simple
User=trading
WorkingDirectory=/opt/trading-bots
ExecStart=/opt/trading-bots/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Security Considerations

- **API Keys**: Store in environment variables, never in code
- **Paper Trading**: Always test strategies in paper mode first
- **Rate Limits**: Respect exchange rate limits
- **Error Handling**: Robust error handling to prevent crashes
- **Monitoring**: Set up alerts for bot failures or unusual activity

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Check Supabase/Neon credentials
   - Verify network connectivity
   - Ensure database tables exist

2. **Exchange Connection Failed**
   - Verify API keys and permissions
   - Check if trading is enabled for your account
   - Ensure correct sandbox/live mode setting

3. **Bot Stops Unexpectedly**
   - Check logs for error messages
   - Verify sufficient account balance
   - Check exchange API status

### Logs Location

- Console logs: Real-time output
- File logs: `logs/trading_bot_YYYY-MM-DD.log`
- Database logs: Check bot_metrics table

## License

MIT License - see LICENSE file for details

## Disclaimer

This software is for educational purposes only. Trading involves substantial risk of loss. Past performance does not guarantee future results. Use at your own risk.