#!/usr/bin/env python3
"""
Setup script to initialize trading platforms in Supabase database.
This script registers all supported platforms with their configurations.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# Add the src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.database import DatabaseManager

# Load environment variables
load_dotenv()

# Platform configurations
PLATFORMS = [
    {
        "id": "binance",
        "name": "Binance",
        "available_markets": ["crypto"],
        "status": "active",
    },
    {
        "id": "coinbase",
        "name": "Coinbase Pro",
        "available_markets": ["crypto"],
        "status": "active",
    },
    {
        "id": "bybit",
        "name": "Bybit",
        "available_markets": ["crypto"],
        "status": "active",
    },
    {
        "id": "bitkub",
        "name": "Bitkub",
        "available_markets": ["crypto"],
        "status": "active",
    },
    {
        "id": "kraken",
        "name": "Kraken",
        "available_markets": ["crypto"],
        "status": "active",
    },
    {
        "id": "alpaca",
        "name": "Alpaca",
        "available_markets": ["stock"],
        "status": "active",
    },
    {
        "id": "td-ameritrade",
        "name": "TD Ameritrade",
        "available_markets": ["stock"],
        "status": "active",
    },
    {
        "id": "interactive-brokers",
        "name": "Interactive Brokers",
        "available_markets": ["stock", "forex"],
        "status": "active",
    },
    {
        "id": "oanda",
        "name": "OANDA",
        "available_markets": ["forex"],
        "status": "active",
    },
    {
        "id": "innovestx",
        "name": "InnovestX",
        "available_markets": ["stock"],
        "status": "active",
    },
]


async def initialize_platforms():
    """Initialize all platforms in the database."""
    try:
        print("Initializing Supabase database with trading platforms...")

        db = DatabaseManager()

        # Create tables if they don't exist
        await db.create_tables()
        print("✓ Database tables verified/created")

        # Register each platform
        success_count = 0
        for platform in PLATFORMS:
            try:
                result = await db.register_platform(platform)
                if result:
                    print(f"✓ Registered platform: {platform['name']}")
                    success_count += 1
                else:
                    print(f"✗ Failed to register platform: {platform['name']}")
            except Exception as e:
                print(f"✗ Error registering {platform['name']}: {e}")

        print(f"\nSuccessfully registered {success_count}/{len(PLATFORMS)} platforms")

        if success_count == len(PLATFORMS):
            print("\n🎉 All platforms initialized successfully!")
            print(
                "Your trading bots can now register themselves and the trading-monitor will be able to read the data."
            )
        else:
            print(
                f"\n⚠️  {len(PLATFORMS) - success_count} platform(s) failed to register. Please check the errors above."
            )

        # Close database connection
        db.close()

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False

    return success_count == len(PLATFORMS)


async def verify_setup():
    """Verify the setup by checking if platforms exist in the database."""
    try:
        print("\nVerifying platform setup...")

        db = DatabaseManager()

        if db.supabase:
            result = db.supabase.table("platforms").select("id, name, status").execute()
            if result.data:
                print(f"\n📊 Found {len(result.data)} platforms in database:")
                for platform in result.data:
                    status_emoji = "✅" if platform["status"] == "active" else "⏸️"
                    print(f"  {status_emoji} {platform['name']} ({platform['id']})")
            else:
                print("❌ No platforms found in database")
        else:
            print("❌ Could not connect to Supabase")

        db.close()

    except Exception as e:
        print(f"❌ Verification failed: {e}")


def check_environment():
    """Check if required environment variables are set."""
    required_vars = ["SUPABASE_URL", "SUPABASE_KEY"]
    missing_vars = []

    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease set these variables in your .env file or environment.")
        print("See .env.example for the required format.")
        return False

    print("✓ Environment variables configured")
    return True


async def main():
    """Main setup function."""
    print("🚀 Trading Bot Platform Setup")
    print("=" * 40)

    # Check environment
    if not check_environment():
        return

    # Initialize platforms
    success = await initialize_platforms()

    # Verify setup
    await verify_setup()

    if success:
        print("\n✅ Setup completed successfully!")
        print("\nNext steps:")
        print(
            "1. Start your trading bots - they will automatically register themselves"
        )
        print("2. Launch the trading-monitor to see your bots and data")
        print("3. Monitor your trading activity in real-time!")
    else:
        print("\n❌ Setup completed with errors.")
        print("Please check the error messages above and retry.")


if __name__ == "__main__":
    asyncio.run(main())
