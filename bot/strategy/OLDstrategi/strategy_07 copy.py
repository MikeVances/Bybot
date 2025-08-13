import pandas as pd
import numpy as np
from typing import Optional, Dict, Any


class Strategy07:
    """
    Стратегия "Пробой - ретест", адаптированная под систему бота.

    Основная идея: торговать пробои зон консолидации по тренду
    с последующим ретестом пробитого уровня.  
    Подход основан на методике TradersGroup: сначала определяем
    направление на старшем таймфрейме (EMA short/long), затем на
    младшем ищем пробой диапазона консолидации. Входим в позицию
    после ретеста уровня пробоя, если подтверждается объемом и
    фильтрами, такими как RSI.  
    
    Параметры
    ----------
    fast_tf : str
        Таймфрейм для поиска пробоев и ретестов (например, '15m').
    slow_tf : str
        Таймфрейм для определения глобального тренда (например, '1h').
    ema_short, ema_long : int
        Периоды EMA на старшем таймфрейме. Если EMA_short > EMA_long,
        тренд считается бычьим; наоборот - медвежьим.
    rsi_period : int
        Период для расчета RSI на быстром таймфрейме.
    rsi_threshold : float
        Значение RSI, выше которого рассматриваются только покупки,
        а ниже - только продажи.
    volume_multiplier : float
        Множитель среднего объема, выше которого всплеск считается
        подтверждением пробоя.
    consolidation_lookback : int
        Количество последних баров на fast_tf для определения диапазона
        консолидации (берется максимум high и минимум low).
    atr_period : int
        Период для ATR, использующийся при расчете стоп-лоссов.
    risk_reward_ratio : float
        Целевое соотношение риск/прибыль, используемое, если размер
        диапазона консолидации слишком мал для адекватной цели.
    stop_loss_atr_multiplier : float
        Множитель ATR для постановки стоп-лосса от противоположного
        уровня консолидации.
    price_step : float
        Шаг округления цены.
    
    Метод `execute` возвращает словарь с сигналом или None, если
    условий для торговли нет. В случае входа генерируется один из
    сигналов: 'BUY' или 'SELL'; если условия разворачиваются,
    возвращаются 'EXIT_LONG' или 'EXIT_SHORT'.
    """

    def __init__(self,
                 fast_tf: str = '15m',
                 slow_tf: str = '1h',
                 ema_short: int = 20,
                 ema_long: int = 50,
                 rsi_period: int = 14,
                 rsi_threshold: float = 50.0,
                 volume_multiplier: float = 2.0,
                 consolidation_lookback: int = 20,
                 atr_period: int = 14,
                 risk_reward_ratio: float = 2.0,
                 stop_loss_atr_multiplier: float = 1.0,
                 price_step: float = 0.1):
        self.fast_tf = fast_tf
        self.slow_tf = slow_tf
        self.ema_short = ema_short
        self.ema_long = ema_long
        self.rsi_period = rsi_period
        self.rsi_threshold = rsi_threshold
        self.volume_multiplier = volume_multiplier
        self.consolidation_lookback = consolidation_lookback
        self.atr_period = atr_period
        self.risk_reward_ratio = risk_reward_ratio
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier
        self.price_step = price_step

    # --- Вспомогательные функции ---
    def round_price(self, price: float) -> float:
        return round(price / self.price_step) * self.price_step

    def _ema(self, series: pd.Series, window: int) -> pd.Series:
        return series.ewm(span=window, adjust=False).mean()

    def _rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        up = delta.clip(lower=0)
        down = (-delta).clip(lower=0)
        roll_up = up.rolling(period).mean()
        roll_down = down.rolling(period).mean()
        rs = roll_up / roll_down
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, df: pd.DataFrame) -> float:
        high = df['high']
        low = df['low']
        close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr_series = tr.rolling(self.atr_period).mean()
        return atr_series.iloc[-1] if not np.isnan(atr_series.iloc[-1]) else (high.iloc[-1] - low.iloc[-1])

    def consolidation_range(self, df: pd.DataFrame) -> tuple:
        """Возвращает (low, high, range) по последним consolidation_lookback барам."""
        if len(df) < self.consolidation_lookback:
            return (np.nan, np.nan, np.nan)
        recent = df.tail(self.consolidation_lookback)
        low_price = recent['low'].min()
        high_price = recent['high'].max()
        return low_price, high_price, (high_price - low_price)

    def is_in_position(self, state: Any) -> bool:
        # Проверяем состояние позиции в BotState
        return state is not None and getattr(state, 'in_position', False)

    # --- Основной метод ---
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
        # убедимся, что достаточно данных для индикаторов
        if len(df_fast) < max(self.consolidation_lookback + 2, self.atr_period, self.rsi_period) or len(df_slow) < self.ema_long:
            return None

        # Текущие значения
        latest_price = df_fast['close'].iloc[-1]
        timestamp = df_fast.index[-1].isoformat() if hasattr(df_fast.index[-1], 'isoformat') else str(df_fast.index[-1])

        # EMA тренд на slow_tf
        df_slow['ema_short'] = self._ema(df_slow['close'], self.ema_short)
        df_slow['ema_long'] = self._ema(df_slow['close'], self.ema_long)
        trend_up = df_slow['ema_short'].iloc[-1] > df_slow['ema_long'].iloc[-1]
        trend_down = df_slow['ema_short'].iloc[-1] < df_slow['ema_long'].iloc[-1]

        # RSI и объём на fast_tf
        rsi_series = self._rsi(df_fast['close'], self.rsi_period)
        current_rsi = rsi_series.iloc[-1]
        avg_volume = df_fast['volume'].rolling(self.consolidation_lookback).mean().iloc[-2]
        # текущий и предыдущий объём
        current_vol = df_fast['volume'].iloc[-1]
        prev_vol = df_fast['volume'].iloc[-2]

        # Диапазон консолидации
        low_cons, high_cons, cons_range = self.consolidation_range(df_fast)
        # избежать NaN
        if np.isnan(cons_range) or cons_range <= 0:
            return None

        # Проверка пробоя на предыдущем баре
        prev_close = df_fast['close'].iloc[-2]
        prev_high = df_fast['high'].iloc[-2]
        prev_low = df_fast['low'].iloc[-2]

        breakout_up = (prev_close > high_cons) and (prev_vol > self.volume_multiplier * avg_volume)
        breakout_down = (prev_close < low_cons) and (prev_vol > self.volume_multiplier * avg_volume)

        # Проверка ретеста на текущем баре
        curr_close = df_fast['close'].iloc[-1]
        curr_low = df_fast['low'].iloc[-1]
        curr_high = df_fast['high'].iloc[-1]
        retest_up = (curr_low <= high_cons) and (curr_close > high_cons)
        retest_down = (curr_high >= low_cons) and (curr_close < low_cons)

        # ATR для стопов
        atr = self.calculate_atr(df_fast)

        # Флаги входа
        in_position = self.is_in_position(state)
        position_side = getattr(state, 'position_side', None) if state is not None else None
        long_signal = False
        short_signal = False

        if not in_position:
            # Вход LONG: пробой вверх + ретест + тренд бычий + RSI > threshold
            if breakout_up and retest_up and trend_up and current_rsi > self.rsi_threshold:
                long_signal = True
            # Вход SHORT: пробой вниз + ретест + тренд медвежий + RSI < threshold
            if breakout_down and retest_down and trend_down and current_rsi < self.rsi_threshold:
                short_signal = True

        # Проверка на открытую позицию
        in_position = self.is_in_position(state)
        position_side = getattr(state, 'position_side', None) if state is not None else None

        # Флаги выхода: выходим, если тренд изменился
        exit_long = False
        exit_short = False
        if in_position:
            if position_side == 'BUY' and not trend_up:
                exit_long = True
            if position_side == 'SELL' and not trend_down:
                exit_short = True

        # Формирование сигналов
        if long_signal:
            entry = self.round_price(curr_close)
            # стоп ниже нижней границы консолидации, учитываем ATR
            stop_loss = self.round_price(low_cons - atr * self.stop_loss_atr_multiplier)
            # цель: диапазон консолидации, отложенный от вершины пробоя
            measured_move = cons_range
            target = high_cons + measured_move
            # если measured_move слишком мал, используем risk_reward_ratio
            rr_target = entry + (entry - stop_loss) * self.risk_reward_ratio
            if target < rr_target:
                target = rr_target
            target = self.round_price(target)
            signal = {
                'symbol': symbol,
                'signal': 'BUY',
                'entry_price': entry,
                'stop_loss': stop_loss,
                'take_profit': target,
                'timestamp': timestamp,
                'strategy': 'BreakoutRetest',
                'params': self.__dict__,
                'indicators': {
                    'ema_short': df_slow['ema_short'].iloc[-1],
                    'ema_long': df_slow['ema_long'].iloc[-1],
                    'rsi': current_rsi,
                    'vol_prev': prev_vol,
                    'vol_avg': avg_volume,
                    'low_cons': low_cons,
                    'high_cons': high_cons,
                    'cons_range': cons_range
                },
                'comment': 'Пробой вверх и ретест уровня консолидации'
            }
            if bybit_api:
                try:
                    bybit_api.log_signal(
                        strategy=signal['strategy'],
                        symbol=symbol,
                        action=signal['signal'],
                        price=entry,
                        stop_loss=stop_loss,
                        take_profit=target,
                        metadata=signal['indicators']
                    )
                except Exception:
                    pass
            return signal

        elif short_signal:
            entry = self.round_price(curr_close)
            stop_loss = self.round_price(high_cons + atr * self.stop_loss_atr_multiplier)
            measured_move = cons_range
            target = low_cons - measured_move
            rr_target = entry - (stop_loss - entry) * self.risk_reward_ratio
            if target > rr_target:
                target = rr_target
            target = self.round_price(target)
            signal = {
                'symbol': symbol,
                'signal': 'SELL',
                'entry_price': entry,
                'stop_loss': stop_loss,
                'take_profit': target,
                'timestamp': timestamp,
                'strategy': 'BreakoutRetest',
                'params': self.__dict__,
                'indicators': {
                    'ema_short': df_slow['ema_short'].iloc[-1],
                    'ema_long': df_slow['ema_long'].iloc[-1],
                    'rsi': current_rsi,
                    'vol_prev': prev_vol,
                    'vol_avg': avg_volume,
                    'low_cons': low_cons,
                    'high_cons': high_cons,
                    'cons_range': cons_range
                },
                'comment': 'Пробой вниз и ретест уровня консолидации'
            }
            if bybit_api:
                try:
                    bybit_api.log_signal(
                        strategy=signal['strategy'],
                        symbol=symbol,
                        action=signal['signal'],
                        price=entry,
                        stop_loss=stop_loss,
                        take_profit=target,
                        metadata=signal['indicators']
                    )
                except Exception:
                    pass
            return signal

        elif exit_long:
            return {'signal': 'EXIT_LONG', 'comment': 'Выход из лонга: изменение тренда', 'timestamp': timestamp}
        elif exit_short:
            return {'signal': 'EXIT_SHORT', 'comment': 'Выход из шорта: изменение тренда', 'timestamp': timestamp}

        return None