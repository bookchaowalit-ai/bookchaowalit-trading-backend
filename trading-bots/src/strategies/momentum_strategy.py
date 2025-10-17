"""Momentum trading strategy implementation."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

from .base_strategy import BaseStrategy, Signal, Position


class MomentumStrategy(BaseStrategy):
    """
    Momentum trading strategy that identifies trends and trades in the direction
    of strong price movements using technical indicators.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.rsi_period = config.get('rsi_period', 14)
        self.ma_short = config.get('ma_short', 10)
        self.ma_long = config.get('ma_long', 30)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        self.volume_threshold = config.get('volume_threshold', 1.5)  # 1.5x average volume
    
    async def analyze(self, symbol: str, timeframe: str = "1h") -> Signal:
        """Analyze market using momentum indicators."""
        try:
            if symbol not in self.historical_data:
                logger.warning(f"No historical data for {symbol}")
                return self._hold_signal(symbol, 0.0)
            
            df = self.historical_data[symbol].copy()
            if len(df) < max(self.ma_long, self.rsi_period) + 10:
                logger.warning(f"Insufficient data for {symbol}")
                return self._hold_signal(symbol, 0.0)
            
            # Calculate technical indicators
            df = self._calculate_indicators(df)
            
            current_price = df['close'].iloc[-1]
            current_rsi = df['rsi'].iloc[-1]
            current_ma_short = df['ma_short'].iloc[-1]
            current_ma_long = df['ma_long'].iloc[-1]
            current_volume_ratio = df['volume_ratio'].iloc[-1]
            
            # Generate trading signal
            signal = self._generate_signal(
                symbol, current_price, current_rsi, 
                current_ma_short, current_ma_long, current_volume_ratio
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Error in momentum strategy analysis for {symbol}: {e}")
            return self._hold_signal(symbol, 0.0)
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators."""
        # RSI (Relative Strength Index)
        df['rsi'] = self._calculate_rsi(df['close'], self.rsi_period)
        
        # Moving Averages
        df['ma_short'] = df['close'].rolling(window=self.ma_short).mean()
        df['ma_long'] = df['close'].rolling(window=self.ma_long).mean()
        
        # Volume analysis
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # Price momentum
        df['price_change'] = df['close'].pct_change()
        df['momentum'] = df['close'] / df['close'].shift(10) - 1  # 10-period momentum
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _generate_signal(
        self, symbol: str, price: float, rsi: float, 
        ma_short: float, ma_long: float, volume_ratio: float
    ) -> Signal:
        """Generate trading signal based on momentum indicators."""
        
        # Check for bullish momentum
        bullish_conditions = [
            ma_short > ma_long,  # Short MA above long MA
            price > ma_short,    # Price above short MA
            rsi > 50,           # RSI above midline
            volume_ratio > self.volume_threshold  # High volume
        ]
        
        # Check for bearish momentum
        bearish_conditions = [
            ma_short < ma_long,  # Short MA below long MA
            price < ma_short,    # Price below short MA
            rsi < 50,           # RSI below midline
            volume_ratio > self.volume_threshold  # High volume
        ]
        
        bullish_score = sum(bullish_conditions)
        bearish_score = sum(bearish_conditions)
        
        # Strong buy signal
        if bullish_score >= 3 and rsi < self.rsi_overbought:
            return Signal(
                action='buy',
                symbol=symbol,
                price=price,
                amount=self.get_position_size(symbol, price, 10000),  # Placeholder balance
                confidence=min(0.9, bullish_score / 4.0),
                timestamp=datetime.now(),
                metadata={
                    'strategy': 'momentum',
                    'rsi': rsi,
                    'ma_signal': 'bullish',
                    'volume_ratio': volume_ratio
                }
            )
        
        # Strong sell signal
        elif bearish_score >= 3 and rsi > self.rsi_oversold:
            return Signal(
                action='sell',
                symbol=symbol,
                price=price,
                amount=self.get_position_size(symbol, price, 10000),  # Placeholder balance
                confidence=min(0.9, bearish_score / 4.0),
                timestamp=datetime.now(),
                metadata={
                    'strategy': 'momentum',
                    'rsi': rsi,
                    'ma_signal': 'bearish',
                    'volume_ratio': volume_ratio
                }
            )
        
        # Hold signal
        return self._hold_signal(symbol, price)
    
    def _hold_signal(self, symbol: str, price: float) -> Signal:
        """Generate hold signal."""
        return Signal(
            action='hold',
            symbol=symbol,
            price=price,
            amount=0.0,
            confidence=0.5,
            timestamp=datetime.now(),
            metadata={'strategy': 'momentum', 'reason': 'no_clear_signal'}
        )
    
    async def should_exit(self, position: Position, current_price: float) -> bool:
        """Determine if position should be closed based on momentum."""
        if position.symbol not in self.historical_data:
            return False
        
        df = self.historical_data[position.symbol].copy()
        if len(df) < self.rsi_period + 5:
            return False
        
        # Calculate current indicators
        df = self._calculate_indicators(df)
        current_rsi = df['rsi'].iloc[-1]
        current_ma_short = df['ma_short'].iloc[-1]
        current_ma_long = df['ma_long'].iloc[-1]
        
        # Exit long position conditions
        if position.side == 'long':
            # RSI overbought or trend reversal
            if (current_rsi > self.rsi_overbought or 
                current_ma_short < current_ma_long or
                current_price < position.entry_price * 0.95):  # 5% stop loss
                return True
        
        # Exit short position conditions
        elif position.side == 'short':
            # RSI oversold or trend reversal
            if (current_rsi < self.rsi_oversold or 
                current_ma_short > current_ma_long or
                current_price > position.entry_price * 1.05):  # 5% stop loss
                return True
        
        return False
    
    def get_position_size(self, symbol: str, price: float, balance: float) -> float:
        """Calculate position size based on volatility and risk."""
        risk_params = self.get_risk_parameters()
        
        # Get recent volatility
        if symbol in self.historical_data:
            df = self.historical_data[symbol]
            if len(df) > 20:
                volatility = df['close'].pct_change().rolling(20).std().iloc[-1]
                # Adjust position size based on volatility
                volatility_adjustment = min(1.0, 0.02 / volatility) if volatility > 0 else 1.0
            else:
                volatility_adjustment = 1.0
        else:
            volatility_adjustment = 1.0
        
        max_position_value = min(
            risk_params['max_position_size'],
            balance * risk_params['risk_per_trade'] * volatility_adjustment
        )
        
        return max_position_value / price
    
    def get_strategy_status(self, symbol: str) -> Dict[str, Any]:
        """Get current strategy status for monitoring."""
        if symbol not in self.historical_data:
            return {}
        
        df = self.historical_data[symbol]
        if len(df) < self.rsi_period + 5:
            return {}
        
        df = self._calculate_indicators(df)
        
        return {
            'rsi': df['rsi'].iloc[-1],
            'ma_short': df['ma_short'].iloc[-1],
            'ma_long': df['ma_long'].iloc[-1],
            'volume_ratio': df['volume_ratio'].iloc[-1],
            'momentum': df['momentum'].iloc[-1],
            'trend': 'bullish' if df['ma_short'].iloc[-1] > df['ma_long'].iloc[-1] else 'bearish'
        }