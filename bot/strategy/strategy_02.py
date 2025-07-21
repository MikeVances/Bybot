import pandas as pd
from typing import Optional, Dict, Any

class Strategy02:
    def __init__(self,
                 delta_window: int = 20,
                 support_window: int = 20,
                 volume_multiplier: float = 1.0,
                 stop_loss_pct: float = 1.0,
                 risk_reward_ratio: float = 2.0,
                 commission_pct: float = 0.05,
                 price_step: float = 0.1,
                 trend_period: int = 50,
                 min_trend_slope: float = 0.0):
        """
        delta_window: окно для расчёта кумулятивной дельты
        support_window: окно для поиска поддержки
        volume_multiplier: фильтр по объёму (если нужно)
        stop_loss_pct: процент стоп-лосса от цены входа
        risk_reward_ratio: соотношение риск/прибыль
        commission_pct: комиссия биржи в %
        price_step: шаг цены для округления
        trend_period: период для фильтра тренда (SMA)
        min_trend_slope: минимальный наклон тренда
        """
        self.delta_window = delta_window
        self.support_window = support_window
        self.volume_multiplier = volume_multiplier
        self.stop_loss_pct = stop_loss_pct
        self.risk_reward_ratio = risk_reward_ratio
        self.commission_pct = commission_pct
        self.price_step = price_step
        self.trend_period = trend_period
        self.min_trend_slope = min_trend_slope

    def round_price(self, price: float) -> float:
        return round(price / self.price_step) * self.price_step

    def is_in_position(self, state) -> bool:
        return state is not None and getattr(state, 'position', None) in ('LONG', 'SHORT')

    def execute(self, market_data, state: Optional[Any] = None, bybit_api: Any = None, symbol: str = 'BTCUSDT') -> Optional[Dict]:
        # Универсальный шаблон: поддержка передачи словаря с таймфреймами
        if isinstance(market_data, dict):
            df = market_data.get('5m')
            if df is None:
                return None
        else:
            df = market_data
        if len(df) < max(self.delta_window, self.support_window, self.trend_period):
            return None

        # Кумулятивная дельта
        if "buy_volume" in df.columns and "sell_volume" in df.columns:
            df["delta"] = df["buy_volume"] - df["sell_volume"]
        elif "delta" not in df.columns:
            df["delta"] = df["close"] - df["open"]
        df["cum_delta"] = df["delta"].rolling(self.delta_window).sum()

        # Фильтр по тренду (SMA)
        df['sma_trend'] = df['close'].rolling(self.trend_period).mean()
        df['trend_slope'] = df['sma_trend'].diff(self.trend_period)
        last_row = df.iloc[-1]
        trend_up = last_row['trend_slope'] > self.min_trend_slope
        trend_down = last_row['trend_slope'] < -self.min_trend_slope

        # Поддержка и сопротивление
        min_support = df['low'].tail(self.support_window).min()
        max_resist = df['high'].tail(self.support_window).max()
        support_zone = min_support * 1.002
        resist_zone = max_resist * 0.998
        price_at_support = last_row['close'] <= support_zone
        price_at_resist = last_row['close'] >= resist_zone

        # Кумулятивная дельта
        cum_delta = last_row['cum_delta']

        # Проверка на открытую позицию
        in_position = self.is_in_position(state)
        position_type = getattr(state, 'position', None) if state is not None else None

        # Динамический SL/TP
        commission = self.commission_pct / 100

        # Условия для входа в лонг
        long_entry = cum_delta > 0 and price_at_support and trend_up and not in_position
        # Условия для входа в шорт
        short_entry = cum_delta < 0 and price_at_resist and trend_down and not in_position
        # Условия для выхода
        exit_long = in_position and position_type == 'LONG' and (cum_delta < 0 or price_at_resist or trend_down)
        exit_short = in_position and position_type == 'SHORT' and (cum_delta > 0 or price_at_support or trend_up)

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
                    'cum_delta': cum_delta,
                    'min_support': min_support,
                    'trend_slope': last_row['trend_slope']
                },
                'strategy': 'TickTimer_CumDelta',
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
                    'cum_delta': cum_delta,
                    'max_resist': max_resist,
                    'trend_slope': last_row['trend_slope']
                },
                'strategy': 'TickTimer_CumDelta',
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
            return {'signal': 'EXIT_LONG', 'comment': 'Выход из лонга по обратному сигналу/тренду/сопротивлению'}
        elif exit_short:
            return {'signal': 'EXIT_SHORT', 'comment': 'Выход из шорта по обратному сигналу/тренду/поддержке'}
        return None 