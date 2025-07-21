import pandas as pd
from typing import Optional, Dict, Any

class Strategy03:
    def __init__(self,
                 fast_tf: str = '5m',
                 slow_tf: str = '1h',
                 fast_window: int = 20,
                 slow_window: int = 20,
                 volume_multiplier: float = 2.0,
                 stop_loss_pct: float = 1.0,
                 risk_reward_ratio: float = 2.0,
                 commission_pct: float = 0.05,
                 price_step: float = 0.1):
        self.fast_tf = fast_tf
        self.slow_tf = slow_tf
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.volume_multiplier = volume_multiplier
        self.stop_loss_pct = stop_loss_pct
        self.risk_reward_ratio = risk_reward_ratio
        self.commission_pct = commission_pct
        self.price_step = price_step

    def round_price(self, price: float) -> float:
        return round(price / self.price_step) * self.price_step

    def is_in_position(self, state) -> bool:
        return state is not None and getattr(state, 'position', None) in ('LONG', 'SHORT')

    def execute(self, all_market_data: Dict[str, pd.DataFrame], state: Optional[Any] = None, bybit_api: Any = None, symbol: str = 'BTCUSDT') -> Optional[Dict]:
        """
        all_market_data: dict с ключами — таймфреймы ('1m', '5m', '1h', ...), значения — DataFrame OHLCV
        """
        # Универсальный шаблон: стратегия сама выбирает нужные ТФ
        df_fast = all_market_data.get(self.fast_tf)
        df_slow = all_market_data.get(self.slow_tf)
        if df_fast is None or df_slow is None:
            return None
        if len(df_fast) < self.fast_window or len(df_slow) < self.slow_window:
            return None

        # Тренд на быстром ТФ
        df_fast['sma_fast'] = df_fast['close'].rolling(self.fast_window).mean()
        trend_fast = df_fast['close'].iloc[-1] > df_fast['sma_fast'].iloc[-1]

        # Тренд на медленном ТФ
        df_slow['sma_slow'] = df_slow['close'].rolling(self.slow_window).mean()
        trend_slow = df_slow['close'].iloc[-1] > df_slow['sma_slow'].iloc[-1]

        # Рост объёма на быстром ТФ
        df_fast['vol_sma'] = df_fast['volume'].rolling(self.fast_window).mean()
        volume_spike = df_fast['volume'].iloc[-1] > self.volume_multiplier * df_fast['vol_sma'].iloc[-1]

        # Проверка на открытую позицию
        in_position = self.is_in_position(state)
        position_type = getattr(state, 'position', None) if state is not None else None
        commission = self.commission_pct / 100

        # Вход в лонг: оба тренда вверх и всплеск объёма
        long_entry = trend_fast and trend_slow and volume_spike and not in_position
        # Вход в шорт: оба тренда вниз и всплеск объёма вниз
        short_entry = (not trend_fast) and (not trend_slow) and volume_spike and not in_position
        # Выходы
        exit_long = in_position and position_type == 'LONG' and (not trend_fast or not trend_slow)
        exit_short = in_position and position_type == 'SHORT' and (trend_fast or trend_slow)

        if long_entry:
            entry_price = self.round_price(df_fast['close'].iloc[-1])
            stop_loss = self.round_price(entry_price * (1 - self.stop_loss_pct / 100 - commission))
            take_profit = self.round_price(entry_price * (1 + (self.stop_loss_pct * self.risk_reward_ratio) / 100 - commission))
            signal = {
                'symbol': symbol,
                'signal': 'BUY',
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': df_fast.index[-1].isoformat() if hasattr(df_fast.index[-1], 'isoformat') else str(df_fast.index[-1]),
                'indicators': {
                    'trend_fast': trend_fast,
                    'trend_slow': trend_slow,
                    'volume': df_fast['volume'].iloc[-1],
                    'vol_sma': df_fast['vol_sma'].iloc[-1]
                },
                'strategy': 'MultiTF_VolumeSpike',
                'params': self.__dict__,
                'comment': 'Вход в лонг по совпадению трендов и всплеску объёма'
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
        elif short_entry:
            entry_price = self.round_price(df_fast['close'].iloc[-1])
            stop_loss = self.round_price(entry_price * (1 + self.stop_loss_pct / 100 + commission))
            take_profit = self.round_price(entry_price * (1 - (self.stop_loss_pct * self.risk_reward_ratio) / 100 + commission))
            signal = {
                'symbol': symbol,
                'signal': 'SELL',
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': df_fast.index[-1].isoformat() if hasattr(df_fast.index[-1], 'isoformat') else str(df_fast.index[-1]),
                'indicators': {
                    'trend_fast': trend_fast,
                    'trend_slow': trend_slow,
                    'volume': df_fast['volume'].iloc[-1],
                    'vol_sma': df_fast['vol_sma'].iloc[-1]
                },
                'strategy': 'MultiTF_VolumeSpike',
                'params': self.__dict__,
                'comment': 'Вход в шорт по совпадению трендов и всплеску объёма'
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
        elif exit_long:
            return {'signal': 'EXIT_LONG', 'comment': 'Выход из лонга по смене тренда'}
        elif exit_short:
            return {'signal': 'EXIT_SHORT', 'comment': 'Выход из шорта по смене тренда'}
        return None 