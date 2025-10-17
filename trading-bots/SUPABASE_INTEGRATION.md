# Trading Bot Supabase Integration

This document explains how to set up and use the trading bots with Supabase integration for the trading-monitor.

## Quick Setup

### 1. Environment Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` and add your Supabase credentials:
```bash
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-supabase-anon-key-here
```

### 2. Initialize Database

Run the setup script to initialize platforms in Supabase:

```bash
python setup_database.py
```

This will:
- Create necessary database tables (if needed)
- Register all supported trading platforms
- Verify the setup

### 3. Start Your Bots

Create a bot configuration and start trading:

```python
from src.bot import TradingBot

bot_config = {
    'id': 'my-btc-bot',
    'name': 'BTC Scalper',
    'platform': 'binance',
    'market': 'crypto',
    'strategy': 'grid',
    'symbols': ['BTC/USDT'],
    'config': {
        'grid_size': 10,
        'grid_spacing': 0.01
    }
}

bot = TradingBot(bot_config)
await bot.initialize()
await bot.run()
```

## Integration Features

### Automatic Registration
- **Platforms**: Automatically registered during bot initialization
- **Bots**: Self-register when they start up
- **Schema Compatibility**: Full compatibility with trading-monitor

### Real-time Data Flow
1. **Trade Execution**: Bots execute trades on exchanges
2. **Data Recording**: Trades saved to Supabase with proper timestamps
3. **Statistics Updates**: Bot performance metrics updated in real-time
4. **Monitor Display**: Trading-monitor reads and displays live data

### Supported Platforms

| Platform | Markets | Status |
|----------|---------|--------|
| Binance | Crypto | ✅ Active |
| Coinbase Pro | Crypto | ✅ Active |
| Bybit | Crypto | ✅ Active |
| Bitkub | Crypto (Thai) | ✅ Active |
| Kraken | Crypto | ✅ Active |
| Alpaca | Stock | ✅ Active |
| TD Ameritrade | Stock | ✅ Active |
| Interactive Brokers | Stock, Forex | ✅ Active |
| OANDA | Forex | ✅ Active |
| InnovestX | Stock (Thai) | ✅ Active |

## Data Schema

### Platforms Table
```sql
platforms (
  id TEXT PRIMARY KEY,
  name TEXT,
  available_markets market_type[],
  status platform_status,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

### Bots Table
```sql
bots (
  id TEXT PRIMARY KEY,
  name TEXT,
  platform_id TEXT REFERENCES platforms(id),
  market market_type,
  status bot_status,
  pnl DECIMAL(12,2),
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

### Trades Table
```sql
trades (
  id TEXT PRIMARY KEY,
  bot_id TEXT REFERENCES bots(id),
  symbol TEXT,
  side trade_side,
  amount DECIMAL(18,8),
  price DECIMAL(18,8),
  pnl DECIMAL(12,2),
  timestamp TIMESTAMP,
  created_at TIMESTAMP
)
```

## Performance Metrics

The system automatically calculates and updates:
- **Total P&L**: Cumulative profit/loss across all trades
- **Today's P&L**: Daily profit/loss (calculated from today's trades)
- **Trade Count**: Total number of executed trades
- **Win Rate**: Percentage of profitable trades
- **Last Trade Time**: Timestamp of most recent trade

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Verify Supabase URL and key in `.env`
   - Check network connectivity
   - Ensure Supabase project is active

2. **Bot Registration Fails**
   - Run `setup_database.py` first
   - Check platform configuration
   - Verify bot configuration format

3. **Trades Not Appearing**
   - Check bot status in database
   - Verify trade execution logs
   - Ensure proper timestamp format

### Logs and Monitoring

Check bot logs for detailed information:
```bash
tail -f bot.log
```

Monitor database through Supabase dashboard:
- Table Editor: View real-time data
- SQL Editor: Run custom queries
- Logs: Check for errors

## Development

### Adding New Platforms

1. Add platform configuration to `setup_database.py`
2. Add platform mapping in `bot.py` `_register_platform()` method
3. Create exchange connector in `exchanges/` directory
4. Update platform list in README

### Custom Strategies

1. Create new strategy class in `strategies/` directory
2. Inherit from `BaseStrategy`
3. Implement required methods: `generate_signal()`, `should_close_position()`
4. Add strategy to `bot.py` `_create_strategy()` method

## Integration with Trading Monitor

The trading-monitor application will automatically:
- Read platform data for overview dashboard
- Display bot status and performance
- Show real-time trade history
- Calculate aggregated statistics
- Provide market-specific views

No additional configuration needed - just ensure both applications use the same Supabase database.
