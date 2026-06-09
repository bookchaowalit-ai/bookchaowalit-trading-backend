#!/bin/bash
# Trading Bot Setup Script
# Run this AFTER rotating API keys

set -e  # Exit on error

echo "🚀 Setting up Trading Bot..."
echo ""

# Navigate to trading bot directory
cd ~/book-dev/book-other/bookchaowalit-trading-backend/trading-bots

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create .env file with your API keys first."
    exit 1
fi

# Check if API keys are still placeholders
if grep -q "test_binance_api_key" .env; then
    echo "⚠️  Warning: API keys still contain placeholder values!"
    echo "Please rotate your API keys before running this script."
    echo "See: ~/solo-empire/docs/ACTION-REQUIRED-SECURITY-TESTING.md"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Verify installation
echo ""
echo "✅ Verifying installation..."
python3 -c "import ccxt; print(f'✅ ccxt {ccxt.__version__}')"
python3 -c "import pandas; print(f'✅ pandas {pandas.__version__}')"
python3 -c "import psycopg2; print(f'✅ psycopg2 {psycopg2.__version__}')"

# Test database connection
echo ""
echo "🔌 Testing database connection..."
python3 -c "
from src.database import Database
try:
    db = Database()
    platforms = db.get_platforms()
    print(f'✅ Database connected! Found {len(platforms)} platforms')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
"

# Test exchange connection (paper mode)
echo ""
echo "📊 Testing exchange connection (paper mode)..."
python3 -c "
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

# Check if using test keys
api_key = os.getenv('BINANCE_TH_API_KEY', '')
if 'test' in api_key.lower():
    print('⚠️  Using test API keys - skipping exchange test')
    print('Please update .env with real API keys after rotation')
else:
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': os.getenv('BINANCE_TH_SECRET_KEY'),
            'sandbox': True  # Use sandbox for testing
        })
        markets = exchange.load_markets()
        print(f'✅ Exchange connected! Found {len(markets)} markets')
    except Exception as e:
        print(f'❌ Exchange connection failed: {e}')
        print('This is OK if you havent rotated keys yet')
"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Rotate API keys (see ACTION-REQUIRED-SECURITY-TESTING.md)"
echo "2. Update .env with new keys"
echo "3. Run: source venv/bin/activate && python3 main.py"
echo ""
