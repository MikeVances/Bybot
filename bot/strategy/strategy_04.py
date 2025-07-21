import pandas as pd
from typing import Optional, Dict, Any

class Strategy04:
    def __init__(self, tf='4h', ema_fast=50, ema_slow=200, volume_window=20, tail_ratio=2.5, stop_loss_buffer=0.0, risk_reward_ratio=2.0):
        self.tf = tf
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.volume_window = volume_window
        self.tail_ratio = tail_ratio
        self.stop_loss_buffer = stop_loss_buffer  # можно добавить небольшой буфер к стопу
        self.risk_reward_ratio = risk_reward_ratio

    def is_in_position(self, state) -> bool:
        return state is not None and getattr(state, 'position', None) in ('LONG', 'SHORT')

    def execute(self, market_data, state: Optional[Any] = None, bybit_api: Any = None, symbol: str = 'BTCUSDT') -> Optional[Dict]:
        # Универсальный шаблон: поддержка передачи словаря с таймфреймами
        if isinstance(market_data, dict):
            df = market_data.get(self.tf)
            if df is None:
                return None
        else:
            df = market_data
        if len(df) < max(self.ema_fast, self.ema_slow, self.volume_window) + 2:
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
        position_type = getattr(state, 'position', None) if state is not None else None

        # Вход после пробоя high/low хвоста
        last = df.iloc[-1]
        signal = None
        if bullish_tail and last['close'] > prev['high'] and not in_position:
            entry_price = last['close']
            stop_loss = prev['low'] - self.stop_loss_buffer
            take_profit = entry_price + (entry_price - stop_loss) * self.risk_reward_ratio
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
                    'body': body
                },
                'strategy': 'KangarooTail',
                'params': self.__dict__,
                'comment': 'Бычий хвост кенгуру'
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
            stop_loss = prev['high'] + self.stop_loss_buffer
            take_profit = entry_price - (stop_loss - entry_price) * self.risk_reward_ratio
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
                    'body': body
                },
                'strategy': 'KangarooTail',
                'params': self.__dict__,
                'comment': 'Медвежий хвост кенгуру'
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
        # Выход по смене тренда
        elif in_position and position_type == 'LONG' and not trend_long:
            return {'signal': 'EXIT_LONG', 'comment': 'Выход из лонга по смене тренда'}
        elif in_position and position_type == 'SHORT' and not trend_short:
            return {'signal': 'EXIT_SHORT', 'comment': 'Выход из шорта по смене тренда'}
        return None 