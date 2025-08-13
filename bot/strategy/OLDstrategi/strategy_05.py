import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple

class Strategy05:
    """
    Торговая стратегия, вдохновлённая выступлением Сергея на SoloConf.
    Она сочетает анализ нескольких таймфреймов, фильтры на основе EMA,
    RSI и объёма, уровни Фибоначчи для целей и ATR для стоп‑лоссов.

    Параметры
    ----------
    fast_tf : str
        Быстрый таймфрейм, из которого берутся данные для входов (например, '15m').
    slow_tf : str
        Медленный таймфрейм для определения тренда (например, '1h').
    ema_short, ema_long : int
        Длины короткой и длинной EMA для оценки направления тренда.
    rsi_period : int
        Период для расчёта RSI.
    rsi_overbought, rsi_oversold : float
        Пороговые значения RSI для зон перекупленности и перепроданности.
    volume_multiplier : float
        Множитель средневзвешенного объёма, выше которого считается всплеск.
    atr_period : int
        Период для расчёта Average True Range.
    fib_lookback : int
        Количество последних баров для определения swing‑high и swing‑low.
    risk_reward_ratio : float
        Фиксированное соотношение риск/прибыль, если уровни Фибоначчи не подходят.
    stop_loss_atr_multiplier : float
        Множитель ATR для размещения стоп‑лосса.
    price_step : float
        Шаг округления цены.
    commission_pct : float
        Комиссия (оставлена для совместимости, но в примере не используется).
    """

    def __init__(self,
                 fast_tf: str = '15m',
                 slow_tf: str = '1h',
                 ema_short: int = 20,
                 ema_long: int = 50,
                 rsi_period: int = 14,
                 rsi_overbought: float = 70,
                 rsi_oversold: float = 30,
                 volume_multiplier: float = 1.5,
                 atr_period: int = 14,
                 fib_lookback: int = 50,
                 risk_reward_ratio: float = 1.5,
                 stop_loss_atr_multiplier: float = 1.0,
                 price_step: float = 0.1,
                 commission_pct: float = 0.05):
        self.fast_tf = fast_tf
        self.slow_tf = slow_tf
        self.ema_short = ema_short
        self.ema_long = ema_long
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.volume_multiplier = volume_multiplier
        self.atr_period = atr_period
        self.fib_lookback = fib_lookback
        self.risk_reward_ratio = risk_reward_ratio
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier
        self.price_step = price_step
        self.commission_pct = commission_pct

    @staticmethod
    def _ema(series: pd.Series, window: int) -> pd.Series:
        return series.ewm(span=window, adjust=False).mean()

    @staticmethod
    def _rsi(series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        up, down = delta.clip(lower=0), -delta.clip(upper=0)
        roll_up = up.rolling(period).mean()
        roll_down = down.rolling(period).mean()
        rs = roll_up / roll_down
        return 100 - (100 / (1 + rs))

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

    def fibonacci_levels(self, df: pd.DataFrame) -> Tuple[float, float, float, float]:
        """
        Вычисляет уровни 0.382 и 0.618 Фибоначчи по последнему диапазону
        (high-low) на интервале fib_lookback. Возвращает (low, level_382, level_618, high).
        """
        if len(df) < self.fib_lookback:
            return (np.nan, np.nan, np.nan, np.nan)
        recent = df.tail(self.fib_lookback)
        high_price = recent['high'].max()
        low_price = recent['low'].min()
        range_ = high_price - low_price
        level_382 = high_price - 0.382 * range_
        level_618 = high_price - 0.618 * range_
        return low_price, level_382, level_618, high_price

    def round_price(self, price: float) -> float:
        return round(price / self.price_step) * self.price_step

    def is_in_position(self, state) -> bool:
        # Проверяем состояние позиции в BotState
        return state is not None and getattr(state, 'in_position', False)

    def execute(
        self,
        all_market_data: Dict[str, pd.DataFrame],
        state: Optional[Any] = None,
        bybit_api: Any = None,
        symbol: str = 'BTCUSDT'
    ) -> Optional[Dict[str, Any]]:
        df_fast = all_market_data.get(self.fast_tf)
        df_slow = all_market_data.get(self.slow_tf)
        if df_fast is None or df_slow is None:
            return None
        if len(df_fast) < max(self.ema_long, self.rsi_period, self.atr_period, self.fib_lookback):
            return None

        # Конвертируем строки в числа
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df_fast.columns:
                df_fast[col] = pd.to_numeric(df_fast[col], errors='coerce')
            if col in df_slow.columns:
                df_slow[col] = pd.to_numeric(df_slow[col], errors='coerce')

        close_fast = df_fast['close']
        # Тренд по EMA на медленном таймфрейме
        df_slow['ema_short'] = self._ema(df_slow['close'], self.ema_short)
        df_slow['ema_long']  = self._ema(df_slow['close'], self.ema_long)
        trend_up = df_slow['ema_short'].iloc[-1] > df_slow['ema_long'].iloc[-1]
        trend_down = df_slow['ema_short'].iloc[-1] < df_slow['ema_long'].iloc[-1]

        # RSI на быстром таймфрейме
        rsi_series = self._rsi(close_fast, self.rsi_period)
        current_rsi = rsi_series.iloc[-1]

        # Всплеск объёма
        df_fast['vol_ma'] = df_fast['volume'].rolling(self.ema_short).mean()
        volume_spike = df_fast['volume'].iloc[-1] > self.volume_multiplier * df_fast['vol_ma'].iloc[-1]

        # ATR и уровни Фибоначчи
        atr = self.calculate_atr(df_fast)
        low, fib_382, fib_618, high = self.fibonacci_levels(df_fast)

        # Проверка на открытую позицию
        in_position = self.is_in_position(state)
        position_side = getattr(state, 'position_side', None) if state is not None else None

        # RSI фильтры: избегаем входов в экстремальных зонах
        rsi_not_overbought = current_rsi < self.rsi_overbought
        rsi_not_oversold = current_rsi > self.rsi_oversold

        # Условия для входа
        long_entry = (not in_position and trend_up and volume_spike and 
                     current_rsi > 50 and rsi_not_overbought)
        short_entry = (not in_position and trend_down and volume_spike and 
                      current_rsi < 50 and rsi_not_oversold)

        exit_long  = in_position and position_side == 'BUY' and (not trend_up or current_rsi > self.rsi_overbought)
        exit_short = in_position and position_side == 'SELL' and (not trend_down or current_rsi < self.rsi_oversold)

        latest_price = self.round_price(close_fast.iloc[-1])

        if long_entry:
            # Тейк‑профит: ближайший уровень Фибоначчи выше цены или фиксированный RR
            if not pd.isna(fib_382) and latest_price < fib_382 < high:
                target = fib_382
            elif not pd.isna(fib_618) and latest_price < fib_618 < high:
                target = fib_618
            else:
                target = latest_price + atr * self.risk_reward_ratio
            stop_loss = latest_price - atr * self.stop_loss_atr_multiplier

            stop_loss = self.round_price(stop_loss)
            target    = self.round_price(target)
            signal = {
                'symbol': symbol,
                'signal': 'BUY',
                'entry_price': latest_price,
                'stop_loss': stop_loss,
                'take_profit': target,
                'timestamp': df_fast.index[-1].isoformat() if hasattr(df_fast.index[-1], 'isoformat') else str(df_fast.index[-1]),
                'indicators': {
                    'ema_short': df_slow['ema_short'].iloc[-1],
                    'ema_long':  df_slow['ema_long'].iloc[-1],
                    'rsi': current_rsi,
                    'volume': df_fast['volume'].iloc[-1],
                    'vol_ma': df_fast['vol_ma'].iloc[-1],
                    'atr': atr,
                    'fib_low': low,
                    'fib_382': fib_382,
                    'fib_618': fib_618,
                    'fib_high': high
                },
                'strategy': 'Fibonacci_RSI_Volume_Optimized',
                'params': self.__dict__,
                'comment': 'Многофреймовый тренд + объём, RSI и уровни Фибоначчи (оптимизированный SL/TP)'
            }
            if bybit_api:
                try:
                    bybit_api.log_signal(
                        strategy=signal['strategy'],
                        symbol=symbol,
                        action=signal['signal'],
                        price=latest_price,
                        stop_loss=stop_loss,
                        take_profit=target,
                        metadata=signal['indicators']
                    )
                except Exception as e:
                    print(f"Ошибка логирования: {e}")
            return signal

        elif short_entry:
            # Тейк‑профит: ближайший уровень Фибоначчи ниже цены или фиксированный RR
            if not pd.isna(fib_618) and latest_price > fib_618 > low:
                target = fib_618
            elif not pd.isna(fib_382) and latest_price > fib_382 > low:
                target = fib_382
            else:
                target = latest_price - atr * self.risk_reward_ratio
            stop_loss = latest_price + atr * self.stop_loss_atr_multiplier

            stop_loss = self.round_price(stop_loss)
            target    = self.round_price(target)
            signal = {
                'symbol': symbol,
                'signal': 'SELL',
                'entry_price': latest_price,
                'stop_loss': stop_loss,
                'take_profit': target,
                'timestamp': df_fast.index[-1].isoformat() if hasattr(df_fast.index[-1], 'isoformat') else str(df_fast.index[-1]),
                'indicators': {
                    'ema_short': df_slow['ema_short'].iloc[-1],
                    'ema_long':  df_slow['ema_long'].iloc[-1],
                    'rsi': current_rsi,
                    'volume': df_fast['volume'].iloc[-1],
                    'vol_ma': df_fast['vol_ma'].iloc[-1],
                    'atr': atr,
                    'fib_low': low,
                    'fib_382': fib_382,
                    'fib_618': fib_618,
                    'fib_high': high
                },
                'strategy': 'Fibonacci_RSI_Volume_Optimized',
                'params': self.__dict__,
                'comment': 'Многофреймовый тренд + объём, RSI и уровни Фибоначчи (оптимизированный SL/TP)'
            }
            if bybit_api:
                try:
                    bybit_api.log_signal(
                        strategy=signal['strategy'],
                        symbol=symbol,
                        action=signal['signal'],
                        price=latest_price,
                        stop_loss=stop_loss,
                        take_profit=target,
                        metadata=signal['indicators']
                    )
                except Exception as e:
                    print(f"Ошибка логирования: {e}")
            return signal

        elif exit_long:
            return {'signal': 'EXIT_LONG', 'comment': 'Выход из лонга: разворот тренда или перекупленность RSI'}

        elif exit_short:
            return {'signal': 'EXIT_SHORT', 'comment': 'Выход из шорта: разворот тренда или перепроданность RSI'}

        return None