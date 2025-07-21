import pandas as pd
from typing import Optional, Dict, Any

class Strategy01:
    def __init__(self, 
                 volume_multiplier: float = 3.0,
                 risk_reward_ratio: float = 2.0,
                 stop_loss_pct: float = 1.0,
                 trend_period: int = 50,
                 min_trend_slope: float = 0.0,
                 commission_pct: float = 0.05,
                 price_step: float = 0.1):
        """
        volume_multiplier: во сколько раз объем должен превысить SMA (по умолчанию 3)
        risk_reward_ratio: соотношение риск/прибыль (по умолчанию 2)
        stop_loss_pct: процент стоп-лосса от цены входа (по умолчанию 1%)
        trend_period: период для фильтра тренда (по умолчанию 50)
        min_trend_slope: минимальный наклон тренда для фильтра (по умолчанию 0)
        commission_pct: комиссия биржи в % (по умолчанию 0.05)
        price_step: шаг цены для округления (по умолчанию 0.1)
        """
        self.volume_multiplier = volume_multiplier
        self.risk_reward_ratio = risk_reward_ratio
        self.stop_loss_pct = stop_loss_pct
        self.trend_period = trend_period
        self.min_trend_slope = min_trend_slope
        self.commission_pct = commission_pct
        self.price_step = price_step

    def round_price(self, price: float) -> float:
        return round(price / self.price_step) * self.price_step

    def is_in_position(self, state) -> bool:
        # Ожидается, что state — это BotState с атрибутом position
        return state is not None and getattr(state, 'position', None) in ('LONG', 'SHORT')

    def execute(self, market_data, state: Optional[Any] = None, bybit_api: Any = None, symbol: str = 'BTCUSDT') -> Optional[Dict]:
        """
        Анализирует данные и возвращает сигнал на сделку или на выход.
        """
        # Универсальный шаблон: поддержка передачи словаря с таймфреймами
        if isinstance(market_data, dict):
            df = market_data.get('5m')
            if df is None:
                return None
        else:
            df = market_data

        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"DataFrame должен содержать колонки: {required_cols}")
        df = df[required_cols].apply(pd.to_numeric, errors='coerce').dropna()
        if len(df) < max(21, self.trend_period):
            return None

        # Индикаторы
        df['vol_sma20'] = df['volume'].rolling(20).mean()
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
        df['sma_trend'] = df['close'].rolling(self.trend_period).mean()
        # Оценка наклона тренда (разница SMA за период)
        df['trend_slope'] = df['sma_trend'].diff(self.trend_period)

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2] if len(df) > 1 else last_row

        # Фильтр по тренду: только если тренд восходящий (лонг) или нисходящий (шорт)
        trend_up = last_row['trend_slope'] > self.min_trend_slope
        trend_down = last_row['trend_slope'] < -self.min_trend_slope

        # Проверка на открытую позицию
        in_position = self.is_in_position(state)

        # Условия для входа в лонг
        volume_long = last_row['volume'] > self.volume_multiplier * last_row['vol_sma20']
        price_long = last_row['close'] > last_row['vwap']
        long_entry = volume_long and price_long and trend_up and not in_position

        # Условия для входа в шорт
        volume_short = last_row['volume'] > self.volume_multiplier * last_row['vol_sma20']
        price_short = last_row['close'] < last_row['vwap']
        short_entry = volume_short and price_short and trend_down and not in_position

        # Условия для выхода (по обратному сигналу или TP/SL)
        exit_long = in_position and state and getattr(state, 'position', None) == 'LONG' and (price_short or trend_down)
        exit_short = in_position and state and getattr(state, 'position', None) == 'SHORT' and (price_long or trend_up)

        # Комиссия
        commission = self.commission_pct / 100

        # Сигналы
        if long_entry:
            entry_price = self.round_price(last_row['close'])
            stop_loss = self.round_price(entry_price * (1 - self.stop_loss_pct / 100 - commission))
            take_profit = self.round_price(entry_price * (1 + (self.stop_loss_pct * self.risk_reward_ratio) / 100 - commission))
            signal = {
                'symbol': symbol,
                'signal': 'BUY',
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': last_row.name.isoformat() if hasattr(last_row.name, 'isoformat') else str(last_row.name),
                'indicators': {
                    'volume': last_row['volume'],
                    'vol_sma20': last_row['vol_sma20'],
                    'vwap': last_row['vwap'],
                    'trend_slope': last_row['trend_slope']
                },
                'strategy': 'VolumeSpike_VWAP',
                'params': self.__dict__,
                'comment': 'Вход в лонг'
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
            entry_price = self.round_price(last_row['close'])
            stop_loss = self.round_price(entry_price * (1 + self.stop_loss_pct / 100 + commission))
            take_profit = self.round_price(entry_price * (1 - (self.stop_loss_pct * self.risk_reward_ratio) / 100 + commission))
            signal = {
                'symbol': symbol,
                'signal': 'SELL',
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': last_row.name.isoformat() if hasattr(last_row.name, 'isoformat') else str(last_row.name),
                'indicators': {
                    'volume': last_row['volume'],
                    'vol_sma20': last_row['vol_sma20'],
                    'vwap': last_row['vwap'],
                    'trend_slope': last_row['trend_slope']
                },
                'strategy': 'VolumeSpike_VWAP',
                'params': self.__dict__,
                'comment': 'Вход в шорт'
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
            return {'signal': 'EXIT_LONG', 'comment': 'Выход из лонга по обратному сигналу или тренду'}
        elif exit_short:
            return {'signal': 'EXIT_SHORT', 'comment': 'Выход из шорта по обратному сигналу или тренду'}
        return None