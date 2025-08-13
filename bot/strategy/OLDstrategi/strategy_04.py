import pandas as pd
import numpy as np
from typing import Optional, Dict, Any

class Strategy04:
    def __init__(self, tf='4h', ema_fast=50, ema_slow=200, volume_window=20, tail_ratio=2.5, 
                 stop_loss_atr_multiplier=1.5, risk_reward_ratio=1.5, atr_period=14, dynamic_tp=True):
        self.tf = tf
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.volume_window = volume_window
        self.tail_ratio = tail_ratio
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier  # Множитель ATR для SL
        self.risk_reward_ratio = risk_reward_ratio  # Уменьшили с 2.0 до 1.5
        self.atr_period = atr_period  # Период для расчета ATR
        self.dynamic_tp = dynamic_tp  # Динамический TP

    def calculate_atr(self, df: pd.DataFrame) -> float:
        """Расчет Average True Range для динамических SL/TP"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()
        
        return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else (high.iloc[-1] - low.iloc[-1])

    def calculate_dynamic_levels(self, df: pd.DataFrame, entry_price: float, side: str) -> tuple:
        """Расчет динамических уровней SL/TP на основе структуры рынка"""
        atr = self.calculate_atr(df)
        
        # Динамический SL на основе ATR
        if side == 'BUY':
            stop_loss = entry_price - (atr * self.stop_loss_atr_multiplier)
            # Динамический TP на основе структуры рынка
            if self.dynamic_tp:
                # Ищем ближайшие уровни сопротивления
                recent_highs = df['high'].tail(20).sort_values(ascending=False)
                potential_tp = None
                
                for high in recent_highs:
                    if high > entry_price and high <= entry_price + (atr * 3):  # Не слишком далеко
                        potential_tp = high
                        break
                
                if potential_tp is None:
                    # Если нет подходящих уровней, используем фиксированный R:R
                    take_profit = entry_price + (atr * self.stop_loss_atr_multiplier * self.risk_reward_ratio)
                else:
                    take_profit = potential_tp
            else:
                take_profit = entry_price + (atr * self.stop_loss_atr_multiplier * self.risk_reward_ratio)
                
        else:  # SELL
            stop_loss = entry_price + (atr * self.stop_loss_atr_multiplier)
            # Динамический TP на основе структуры рынка
            if self.dynamic_tp:
                # Ищем ближайшие уровни поддержки
                recent_lows = df['low'].tail(20).sort_values(ascending=True)
                potential_tp = None
                
                for low in recent_lows:
                    if low < entry_price and low >= entry_price - (atr * 3):  # Не слишком далеко
                        potential_tp = low
                        break
                
                if potential_tp is None:
                    # Если нет подходящих уровней, используем фиксированный R:R
                    take_profit = entry_price - (atr * self.stop_loss_atr_multiplier * self.risk_reward_ratio)
                else:
                    take_profit = potential_tp
            else:
                take_profit = entry_price - (atr * self.stop_loss_atr_multiplier * self.risk_reward_ratio)
        
        return round(stop_loss, 1), round(take_profit, 1)  # Округление для BTCUSDT

    def is_in_position(self, state) -> bool:
        # Проверяем состояние позиции в BotState
        return state is not None and getattr(state, 'in_position', False)

    def execute(self, market_data, state: Optional[Any] = None, bybit_api: Any = None, symbol: str = 'BTCUSDT') -> Optional[Dict]:
        # Универсальный шаблон: поддержка передачи словаря с таймфреймами
        if isinstance(market_data, dict):
            df = market_data.get(self.tf)
            if df is None:
                return None
        else:
            df = market_data
        if len(df) < max(self.ema_fast, self.ema_slow, self.volume_window, self.atr_period) + 2:
            return None

        # EMA фильтр
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow).mean()
        trend_long = df['ema_fast'].iloc[-2] < df['ema_slow'].iloc[-2]
        trend_short = df['ema_fast'].iloc[-2] > df['ema_slow'].iloc[-2]

        # Объём
        df['vol_sma'] = df['volume'].rolling(self.volume_window).mean()
        high_volume = df['volume'].iloc[-2] > df['vol_sma'].iloc[-2]

        # Хвосты
        prev = df.iloc[-2]
        body = abs(prev['close'] - prev['open'])
        candle_range = prev['high'] - prev['low']
        lower_shadow = min(prev['open'], prev['close']) - prev['low']
        upper_shadow = prev['high'] - max(prev['open'], prev['close'])

        bullish_tail = (
            lower_shadow > self.tail_ratio * body and
            body < 0.3 * candle_range and
            prev['close'] > prev['open'] and
            trend_long and
            high_volume
        )
        bearish_tail = (
            upper_shadow > self.tail_ratio * body and
            body < 0.3 * candle_range and
            prev['close'] < prev['open'] and
            trend_short and
            high_volume
        )

        # Проверка на открытую позицию
        in_position = self.is_in_position(state)
        position_side = getattr(state, 'position_side', None) if state is not None else None

        # Вход после пробоя high/low хвоста
        last = df.iloc[-1]
        signal = None
        if bullish_tail and last['close'] > prev['high'] and not in_position:
            entry_price = last['close']
            stop_loss, take_profit = self.calculate_dynamic_levels(df, entry_price, 'BUY')
            
            signal = {
                'signal': 'BUY',
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': last.name.isoformat() if hasattr(last.name, 'isoformat') else str(last.name),
                'indicators': {
                    'trend_long': trend_long,
                    'high_volume': high_volume,
                    'lower_shadow': lower_shadow,
                    'body': body,
                    'atr': self.calculate_atr(df)
                },
                'strategy': 'KangarooTail_Optimized',
                'params': self.__dict__,
                'comment': 'Бычий хвост кенгуру (оптимизированный SL/TP)'
            }
            if bybit_api:
                try:
                    bybit_api.log_signal(
                        strategy=signal['strategy'],
                        symbol=symbol,
                        action=signal['signal'],
                        price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        metadata=signal['indicators']
                    )
                except Exception as e:
                    print(f"Ошибка логирования: {e}")
            return signal
        elif bearish_tail and last['close'] < prev['low'] and not in_position:
            entry_price = last['close']
            stop_loss, take_profit = self.calculate_dynamic_levels(df, entry_price, 'SELL')
            
            signal = {
                'signal': 'SELL',
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': last.name.isoformat() if hasattr(last.name, 'isoformat') else str(last.name),
                'indicators': {
                    'trend_short': trend_short,
                    'high_volume': high_volume,
                    'upper_shadow': upper_shadow,
                    'body': body,
                    'atr': self.calculate_atr(df)
                },
                'strategy': 'KangarooTail_Optimized',
                'params': self.__dict__,
                'comment': 'Медвежий хвост кенгуру (оптимизированный SL/TP)'
            }
            if bybit_api:
                try:
                    bybit_api.log_signal(
                        strategy=signal['strategy'],
                        symbol=symbol,
                        action=signal['signal'],
                        price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        metadata=signal['indicators']
                    )
                except Exception as e:
                    print(f"Ошибка логирования: {e}")
            return signal
        elif in_position and position_side == 'BUY' and last['close'] < prev['low']:
            return {'signal': 'EXIT_LONG', 'comment': 'Выход из лонга по пробою поддержки'}
        elif in_position and position_side == 'SELL' and last['close'] > prev['high']:
            return {'signal': 'EXIT_SHORT', 'comment': 'Выход из шорта по пробою сопротивления'}
        return None 