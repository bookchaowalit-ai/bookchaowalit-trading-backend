"""Grid trading strategy implementation."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

from .base_strategy import BaseStrategy, Signal, Position


class GridTradingStrategy(BaseStrategy):
    """
    Grid trading strategy that places buy and sell orders at regular intervals
    around the current price to profit from market volatility.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.grid_levels = config.get('grid_levels', 10)
        self.grid_spacing = config.get('grid_spacing', 0.01)  # 1% spacing
        # base_order_size is a quote-currency notional (e.g. 50 USDT per level),
        # converted to a base quantity at each level's price.
        self.base_order_size = config.get('base_order_size', 100)
        self.active_grids: Dict[str, List[Dict]] = {}
    
    async def analyze(self, symbol: str, timeframe: str = "1h") -> Signal:
        """Analyze market and generate grid trading signals."""
        try:
            if symbol not in self.historical_data:
                logger.warning(f"No historical data for {symbol}")
                return Signal(
                    action='hold',
                    symbol=symbol,
                    price=0.0,
                    amount=0.0,
                    confidence=0.0,
                    timestamp=datetime.now()
                )
            
            df = self.historical_data[symbol]
            if len(df) < 20:
                logger.warning(f"Insufficient data for {symbol}")
                return Signal(
                    action='hold',
                    symbol=symbol,
                    price=0.0,
                    amount=0.0,
                    confidence=0.0,
                    timestamp=datetime.now()
                )
            
            current_price = df['close'].iloc[-1]
            
            # Initialize grid if not exists
            if symbol not in self.active_grids:
                self._initialize_grid(symbol, current_price)
            
            # Check for grid trading opportunities
            signal = self._check_grid_signals(symbol, current_price)
            
            return signal
            
        except Exception as e:
            logger.error(f"Error in grid strategy analysis for {symbol}: {e}")
            return Signal(
                action='hold',
                symbol=symbol,
                price=0.0,
                amount=0.0,
                confidence=0.0,
                timestamp=datetime.now()
            )
    
    def _level_quantity(self, price: float) -> float:
        """Base-asset quantity for one grid level, capped by max_position_size notional."""
        if price <= 0:
            return 0.0
        notional = min(self.base_order_size, self.get_risk_parameters()['max_position_size'])
        return notional / price

    def _initialize_grid(self, symbol: str, center_price: float):
        """Initialize grid levels around current price."""
        grid_levels = []
        
        # Create buy levels below current price
        for i in range(1, self.grid_levels // 2 + 1):
            buy_price = center_price * (1 - self.grid_spacing * i)
            grid_levels.append({
                'type': 'buy',
                'price': buy_price,
                'amount': self._level_quantity(buy_price),
                'active': True
            })
        
        # Create sell levels above current price
        for i in range(1, self.grid_levels // 2 + 1):
            sell_price = center_price * (1 + self.grid_spacing * i)
            grid_levels.append({
                'type': 'sell',
                'price': sell_price,
                'amount': self._level_quantity(sell_price),
                'active': True
            })
        
        self.active_grids[symbol] = grid_levels
        logger.info(f"Initialized grid for {symbol} with {len(grid_levels)} levels around ${center_price:.4f}")
    
    def _check_grid_signals(self, symbol: str, current_price: float) -> Signal:
        """Check if current price triggers any grid levels."""
        grid_levels = self.active_grids[symbol]
        
        for level in grid_levels:
            if not level['active']:
                continue
            
            # Check buy levels (price went down to buy level)
            if level['type'] == 'buy' and current_price <= level['price']:
                level['active'] = False  # Mark as triggered
                
                return Signal(
                    action='buy',
                    symbol=symbol,
                    price=level['price'],
                    amount=level['amount'],
                    confidence=0.8,
                    timestamp=datetime.now(),
                    metadata={'strategy': 'grid', 'level_type': 'buy'}
                )
            
            # Check sell levels (price went up to sell level)
            elif level['type'] == 'sell' and current_price >= level['price']:
                level['active'] = False  # Mark as triggered
                
                return Signal(
                    action='sell',
                    symbol=symbol,
                    price=level['price'],
                    amount=level['amount'],
                    confidence=0.8,
                    timestamp=datetime.now(),
                    metadata={'strategy': 'grid', 'level_type': 'sell'}
                )
        
        return Signal(
            action='hold',
            symbol=symbol,
            price=current_price,
            amount=0.0,
            confidence=0.5,
            timestamp=datetime.now(),
            metadata={'strategy': 'grid', 'level_type': 'hold'}
        )
    
    async def should_exit(self, position: Position, current_price: float) -> bool:
        """Grid strategy typically doesn't exit positions manually."""
        # Grid strategy relies on opposite grid levels to close positions
        # But we can implement basic risk management
        
        risk_params = self.get_risk_parameters()
        
        # Check stop loss
        if position.side == 'long':
            stop_loss_price = position.entry_price * (1 - risk_params['stop_loss'])
            if current_price <= stop_loss_price:
                logger.warning(f"Stop loss triggered for {position.symbol} at {current_price}")
                return True
        else:  # short
            stop_loss_price = position.entry_price * (1 + risk_params['stop_loss'])
            if current_price >= stop_loss_price:
                logger.warning(f"Stop loss triggered for {position.symbol} at {current_price}")
                return True
        
        return False
    
    def get_position_size(self, symbol: str, price: float, balance: float) -> float:
        """Calculate position size for grid trading."""
        risk_params = self.get_risk_parameters()
        max_position_value = min(
            risk_params['max_position_size'],
            balance * risk_params['risk_per_trade']
        )
        
        return max_position_value / price
    
    def update_grid_after_fill(self, symbol: str, filled_price: float, side: str):
        """Update grid levels after an order is filled."""
        if symbol not in self.active_grids:
            return
        
        # Reactivate the opposite level
        grid_levels = self.active_grids[symbol]
        
        if side == 'buy':
            # After buying, activate a sell level above
            sell_price = filled_price * (1 + self.grid_spacing)
            for level in grid_levels:
                if level['type'] == 'sell' and abs(level['price'] - sell_price) < (sell_price * 0.001):
                    level['active'] = True
                    break
        
        elif side == 'sell':
            # After selling, activate a buy level below
            buy_price = filled_price * (1 - self.grid_spacing)
            for level in grid_levels:
                if level['type'] == 'buy' and abs(level['price'] - buy_price) < (buy_price * 0.001):
                    level['active'] = True
                    break
        
        logger.info(f"Updated grid for {symbol} after {side} at ${filled_price:.4f}")
    
    def get_grid_status(self, symbol: str) -> Dict[str, Any]:
        """Get current grid status for monitoring."""
        if symbol not in self.active_grids:
            return {}
        
        grid_levels = self.active_grids[symbol]
        active_buys = len([l for l in grid_levels if l['type'] == 'buy' and l['active']])
        active_sells = len([l for l in grid_levels if l['type'] == 'sell' and l['active']])
        
        return {
            'total_levels': len(grid_levels),
            'active_buy_levels': active_buys,
            'active_sell_levels': active_sells,
            'grid_spacing': self.grid_spacing,
            'base_order_size': self.base_order_size
        }