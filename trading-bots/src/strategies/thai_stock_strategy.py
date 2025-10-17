"""Thai stock market specific trading strategy."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, time
from loguru import logger

from .base_strategy import BaseStrategy, Signal, Position


class ThaiStockStrategy(BaseStrategy):
    """
    Trading strategy optimized for Thai stock market (SET) characteristics.
    Considers market hours, volatility patterns, and local market behavior.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.rsi_period = config.get('rsi_period', 14)
        self.ma_short = config.get('ma_short', 5)
        self.ma_long = config.get('ma_long', 20)
        self.volume_ma_period = config.get('volume_ma_period', 10)
        self.volatility_threshold = config.get('volatility_threshold', 0.02)  # 2%
        
        # Thai market specific parameters
        self.morning_session_start = time(10, 0)  # 10:00 AM
        self.morning_session_end = time(12, 30)   # 12:30 PM
        self.afternoon_session_start = time(14, 30)  # 2:30 PM
        self.afternoon_session_end = time(16, 30)    # 4:30 PM
        
        # Common Thai stock sectors and their characteristics
        self.sector_configs = {
            'banking': {'symbols': ['KBANK', 'SCB', 'BBL', 'KTB', 'TCAP'], 'volatility_adj': 0.8},
            'energy': {'symbols': ['PTT', 'PTTEP', 'PTTGC', 'TOP', 'BANPU'], 'volatility_adj': 1.2},
            'retail': {'symbols': ['CPALL', 'HMPRO', 'COM7', 'MAKRO'], 'volatility_adj': 1.0},
            'telecom': {'symbols': ['ADVANC', 'INTUCH', 'TRUE', 'DTAC'], 'volatility_adj': 0.9},
            'property': {'symbols': ['CPN', 'LH', 'AP', 'SPALI'], 'volatility_adj': 1.1}
        }
    
    async def analyze(self, symbol: str, timeframe: str = "1h") -> Signal:
        """Analyze Thai stock with market-specific considerations."""
        try:
            if symbol not in self.historical_data:
                logger.warning(f"No historical data for {symbol}")
                return self._hold_signal(symbol, 0.0)
            
            df = self.historical_data[symbol].copy()
            if len(df) < max(self.ma_long, self.rsi_period) + 10:
                logger.warning(f"Insufficient data for {symbol}")
                return self._hold_signal(symbol, 0.0)
            
            # Check if market is open
            current_time = datetime.now().time()
            if not self._is_market_open(current_time):
                return self._hold_signal(symbol, 0.0)
            
            # Calculate indicators
            df = self._calculate_thai_indicators(df, symbol)
            
            current_price = df['close'].iloc[-1]
            
            # Generate signal based on Thai market patterns
            signal = self._generate_thai_signal(symbol, df, current_price)
            
            return signal
            
        except Exception as e:
            logger.error(f"Error in Thai stock strategy analysis for {symbol}: {e}")
            return self._hold_signal(symbol, 0.0)
    
    def _is_market_open(self, current_time: time) -> bool:
        """Check if Thai stock market is currently open."""
        # Morning session: 10:00 - 12:30
        if self.morning_session_start <= current_time <= self.morning_session_end:
            return True
        
        # Afternoon session: 14:30 - 16:30
        if self.afternoon_session_start <= current_time <= self.afternoon_session_end:
            return True
        
        return False
    
    def _get_sector_for_symbol(self, symbol: str) -> str:
        """Identify sector for a given symbol."""
        for sector, config in self.sector_configs.items():
            if symbol in config['symbols']:
                return sector
        return 'general'
    
    def _calculate_thai_indicators(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Calculate indicators optimized for Thai market."""
        # Basic indicators
        df['rsi'] = self._calculate_rsi(df['close'], self.rsi_period)
        df['ma_short'] = df['close'].rolling(window=self.ma_short).mean()
        df['ma_long'] = df['close'].rolling(window=self.ma_long).mean()
        
        # Volume analysis (important in Thai market)
        df['volume_ma'] = df['volume'].rolling(window=self.volume_ma_period).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # Volatility (Thai stocks can be volatile)
        df['volatility'] = df['close'].pct_change().rolling(window=20).std()
        
        # Price momentum with Thai market adjustment
        df['momentum_5'] = df['close'] / df['close'].shift(5) - 1
        df['momentum_10'] = df['close'] / df['close'].shift(10) - 1
        
        # Support and resistance levels (important for Thai retail investors)
        df['support'] = df['low'].rolling(window=20).min()
        df['resistance'] = df['high'].rolling(window=20).max()
        
        # Sector-specific adjustments
        sector = self._get_sector_for_symbol(symbol)
        if sector in self.sector_configs:
            volatility_adj = self.sector_configs[sector]['volatility_adj']
            df['adjusted_volatility'] = df['volatility'] * volatility_adj
        else:
            df['adjusted_volatility'] = df['volatility']
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _generate_thai_signal(self, symbol: str, df: pd.DataFrame, current_price: float) -> Signal:
        """Generate trading signal optimized for Thai market behavior."""
        
        # Get current values
        current_rsi = df['rsi'].iloc[-1]
        current_ma_short = df['ma_short'].iloc[-1]
        current_ma_long = df['ma_long'].iloc[-1]
        current_volume_ratio = df['volume_ratio'].iloc[-1]
        current_volatility = df['adjusted_volatility'].iloc[-1]
        current_momentum_5 = df['momentum_5'].iloc[-1]
        
        # Thai market specific conditions
        sector = self._get_sector_for_symbol(symbol)
        
        # Adjust thresholds based on sector
        if sector == 'banking':
            rsi_oversold, rsi_overbought = 25, 75  # Banks are more stable
            volume_threshold = 1.2
        elif sector == 'energy':
            rsi_oversold, rsi_overbought = 35, 65  # Energy is more volatile
            volume_threshold = 1.5
        else:
            rsi_oversold, rsi_overbought = 30, 70  # Default
            volume_threshold = 1.3
        
        # Check market session for different strategies
        current_time = datetime.now().time()
        is_morning_session = self.morning_session_start <= current_time <= self.morning_session_end
        
        # Morning session: More conservative (retail investors active)
        if is_morning_session:
            confidence_multiplier = 0.8
        else:  # Afternoon session: More aggressive (institutional activity)
            confidence_multiplier = 1.0
        
        # Bullish conditions
        bullish_conditions = [
            current_ma_short > current_ma_long,  # Uptrend
            current_price > current_ma_short,    # Price above short MA
            current_rsi > 50 and current_rsi < rsi_overbought,  # RSI in bullish zone
            current_volume_ratio > volume_threshold,  # High volume
            current_momentum_5 > 0.01,  # Positive 5-day momentum
            current_volatility < self.volatility_threshold  # Not too volatile
        ]
        
        # Bearish conditions
        bearish_conditions = [
            current_ma_short < current_ma_long,  # Downtrend
            current_price < current_ma_short,    # Price below short MA
            current_rsi < 50 and current_rsi > rsi_oversold,  # RSI in bearish zone
            current_volume_ratio > volume_threshold,  # High volume
            current_momentum_5 < -0.01,  # Negative 5-day momentum
            current_volatility < self.volatility_threshold  # Not too volatile
        ]
        
        bullish_score = sum(bullish_conditions)
        bearish_score = sum(bearish_conditions)
        
        # Generate signals
        if bullish_score >= 4:
            confidence = min(0.9, (bullish_score / 6.0) * confidence_multiplier)
            return Signal(
                action='buy',
                symbol=symbol,
                price=current_price,
                amount=self.get_position_size(symbol, current_price, 100000),  # 100k THB balance
                confidence=confidence,
                timestamp=datetime.now(),
                metadata={
                    'strategy': 'thai_stock',
                    'sector': sector,
                    'session': 'morning' if is_morning_session else 'afternoon',
                    'rsi': current_rsi,
                    'volume_ratio': current_volume_ratio,
                    'bullish_score': bullish_score
                }
            )
        
        elif bearish_score >= 4:
            confidence = min(0.9, (bearish_score / 6.0) * confidence_multiplier)
            return Signal(
                action='sell',
                symbol=symbol,
                price=current_price,
                amount=self.get_position_size(symbol, current_price, 100000),
                confidence=confidence,
                timestamp=datetime.now(),
                metadata={
                    'strategy': 'thai_stock',
                    'sector': sector,
                    'session': 'morning' if is_morning_session else 'afternoon',
                    'rsi': current_rsi,
                    'volume_ratio': current_volume_ratio,
                    'bearish_score': bearish_score
                }
            )
        
        return self._hold_signal(symbol, current_price)
    
    def _hold_signal(self, symbol: str, price: float) -> Signal:
        """Generate hold signal."""
        return Signal(
            action='hold',
            symbol=symbol,
            price=price,
            amount=0.0,
            confidence=0.5,
            timestamp=datetime.now(),
            metadata={'strategy': 'thai_stock', 'reason': 'no_clear_signal'}
        )
    
    async def should_exit(self, position: Position, current_price: float) -> bool:
        """Determine if position should be closed (Thai market specific)."""
        if position.symbol not in self.historical_data:
            return False
        
        df = self.historical_data[position.symbol].copy()
        if len(df) < self.rsi_period + 5:
            return False
        
        # Calculate current indicators
        df = self._calculate_thai_indicators(df, position.symbol)
        current_rsi = df['rsi'].iloc[-1]
        current_ma_short = df['ma_short'].iloc[-1]
        current_ma_long = df['ma_long'].iloc[-1]
        
        # Sector-specific exit conditions
        sector = self._get_sector_for_symbol(position.symbol)
        
        # Exit long position conditions
        if position.side == 'long':
            # RSI overbought or trend reversal
            if (current_rsi > 75 or 
                current_ma_short < current_ma_long or
                current_price < position.entry_price * 0.95):  # 5% stop loss
                return True
        
        # Exit short position conditions
        elif position.side == 'short':
            # RSI oversold or trend reversal
            if (current_rsi < 25 or 
                current_ma_short > current_ma_long or
                current_price > position.entry_price * 1.05):  # 5% stop loss
                return True
        
        return False
    
    def get_position_size(self, symbol: str, price: float, balance: float) -> float:
        """Calculate position size for Thai stocks (in shares)."""
        risk_params = self.get_risk_parameters()
        sector = self._get_sector_for_symbol(symbol)
        
        # Sector-specific risk adjustment
        if sector == 'banking':
            risk_multiplier = 1.2  # Banks are more stable
        elif sector == 'energy':
            risk_multiplier = 0.8  # Energy is more volatile
        else:
            risk_multiplier = 1.0
        
        max_position_value = min(
            risk_params['max_position_size'],
            balance * risk_params['risk_per_trade'] * risk_multiplier
        )
        
        # Convert to shares (Thai stocks trade in whole shares)
        shares = int(max_position_value / price)
        
        # Minimum lot size for Thai stocks is usually 100 shares
        return max(100, (shares // 100) * 100)
    
    def get_thai_market_status(self) -> Dict[str, Any]:
        """Get Thai market specific status information."""
        current_time = datetime.now().time()
        
        return {
            'market_open': self._is_market_open(current_time),
            'current_session': self._get_current_session(current_time),
            'next_session_start': self._get_next_session_start(current_time),
            'supported_sectors': list(self.sector_configs.keys())
        }
    
    def _get_current_session(self, current_time: time) -> str:
        """Get current trading session."""
        if self.morning_session_start <= current_time <= self.morning_session_end:
            return 'morning'
        elif self.afternoon_session_start <= current_time <= self.afternoon_session_end:
            return 'afternoon'
        else:
            return 'closed'
    
    def _get_next_session_start(self, current_time: time) -> str:
        """Get next session start time."""
        if current_time < self.morning_session_start:
            return f"{self.morning_session_start.strftime('%H:%M')} (Morning Session)"
        elif self.morning_session_end < current_time < self.afternoon_session_start:
            return f"{self.afternoon_session_start.strftime('%H:%M')} (Afternoon Session)"
        elif current_time > self.afternoon_session_end:
            return f"{self.morning_session_start.strftime('%H:%M')} (Next Day Morning)"
        else:
            return "Currently in session"