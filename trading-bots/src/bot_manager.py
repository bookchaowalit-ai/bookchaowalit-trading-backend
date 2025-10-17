"""Bot manager for orchestrating multiple trading bots."""

import asyncio
import json
from typing import Dict, List, Any
from pathlib import Path
from loguru import logger

from .bot import TradingBot
from .config import Config


class BotManager:
    """Manages multiple trading bots and their lifecycle."""
    
    def __init__(self):
        self.bots: Dict[str, TradingBot] = {}
        self.bot_tasks: Dict[str, asyncio.Task] = {}
        self.is_running = False
    
    async def load_bot_configs(self, config_path: str = "bot_configs.json") -> List[Dict[str, Any]]:
        """Load bot configurations from file."""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Config file {config_path} not found, creating default configs")
                return self._create_default_configs()
            
            with open(config_file, 'r') as f:
                configs = json.load(f)
            
            logger.info(f"Loaded {len(configs)} bot configurations")
            return configs
            
        except Exception as e:
            logger.error(f"Failed to load bot configs: {e}")
            return []
    
    def _create_default_configs(self) -> List[Dict[str, Any]]:
        """Create default bot configurations."""
        return [
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
            },
            {
                "id": "eth_momentum_bot",
                "name": "ETH Momentum Bot",
                "platform": "binance",
                "market": "crypto",
                "strategy": "momentum",
                "symbols": ["ETH/USDT"],
                "config": {
                    "rsi_period": 14,
                    "ma_short": 10,
                    "ma_long": 30,
                    "rsi_oversold": 30,
                    "rsi_overbought": 70,
                    "max_position_size": 800,
                    "risk_per_trade": 0.015
                }
            }
        ]
    
    async def start_bot(self, bot_config: Dict[str, Any]) -> bool:
        """Start a single trading bot."""
        try:
            bot_id = bot_config['id']
            
            if bot_id in self.bots:
                logger.warning(f"Bot {bot_id} is already running")
                return False
            
            # Create and initialize bot
            bot = TradingBot(bot_config)
            if not await bot.initialize():
                logger.error(f"Failed to initialize bot {bot_id}")
                return False
            
            # Start bot in background task
            task = asyncio.create_task(bot.run())
            
            self.bots[bot_id] = bot
            self.bot_tasks[bot_id] = task
            
            logger.info(f"Started bot {bot_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start bot {bot_config.get('id', 'unknown')}: {e}")
            return False
    
    async def stop_bot(self, bot_id: str) -> bool:
        """Stop a specific trading bot."""
        try:
            if bot_id not in self.bots:
                logger.warning(f"Bot {bot_id} not found")
                return False
            
            # Stop the bot
            await self.bots[bot_id].stop()
            
            # Cancel the task
            if bot_id in self.bot_tasks:
                self.bot_tasks[bot_id].cancel()
                try:
                    await self.bot_tasks[bot_id]
                except asyncio.CancelledError:
                    pass
                del self.bot_tasks[bot_id]
            
            del self.bots[bot_id]
            
            logger.info(f"Stopped bot {bot_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop bot {bot_id}: {e}")
            return False
    
    async def start_all_bots(self, config_path: str = "bot_configs.json"):
        """Start all bots from configuration."""
        try:
            Config.validate_config()
            
            bot_configs = await self.load_bot_configs(config_path)
            
            for config in bot_configs:
                await self.start_bot(config)
            
            self.is_running = True
            logger.info(f"Started {len(self.bots)} trading bots")
            
        except Exception as e:
            logger.error(f"Failed to start bots: {e}")
    
    async def stop_all_bots(self):
        """Stop all running bots."""
        try:
            bot_ids = list(self.bots.keys())
            
            for bot_id in bot_ids:
                await self.stop_bot(bot_id)
            
            self.is_running = False
            logger.info("Stopped all trading bots")
            
        except Exception as e:
            logger.error(f"Failed to stop all bots: {e}")
    
    def get_bot_status(self, bot_id: str) -> Dict[str, Any]:
        """Get status of a specific bot."""
        if bot_id not in self.bots:
            return {}
        
        return self.bots[bot_id].get_status()
    
    def get_all_bot_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all bots."""
        return {
            bot_id: bot.get_status() 
            for bot_id, bot in self.bots.items()
        }
    
    async def monitor_bots(self):
        """Monitor bot health and restart if needed."""
        while self.is_running:
            try:
                # Check for failed tasks
                for bot_id, task in list(self.bot_tasks.items()):
                    if task.done() and not task.cancelled():
                        logger.warning(f"Bot {bot_id} task completed unexpectedly")
                        
                        # Try to restart the bot
                        if bot_id in self.bots:
                            bot_config = self.bots[bot_id].config
                            await self.stop_bot(bot_id)
                            await asyncio.sleep(5)  # Wait before restart
                            await self.start_bot(bot_config)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in bot monitoring: {e}")
                await asyncio.sleep(60)
    
    async def run(self, config_path: str = "bot_configs.json"):
        """Run the bot manager."""
        try:
            logger.info("Starting Bot Manager")
            
            # Start all bots
            await self.start_all_bots(config_path)
            
            # Start monitoring
            monitor_task = asyncio.create_task(self.monitor_bots())
            
            # Keep running until interrupted
            try:
                await monitor_task
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
            finally:
                monitor_task.cancel()
                await self.stop_all_bots()
                
        except Exception as e:
            logger.error(f"Error in bot manager: {e}")
        finally:
            logger.info("Bot Manager stopped")