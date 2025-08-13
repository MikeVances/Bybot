import pandas as pd
import numpy as np
from typing import Optional, Dict, Any


class Strategy06:
    """
    Стратегия ловли разворота на кульминации объема.

    Эта реализация адаптирована под общий интерфейс торгового бота
    (прием словаря `all_market_data` с ключами таймфреймов, использование
    объекта `state` для хранения позиции и `bybit_api` для логирования).  

    Идея стратегии:
      * На младшем таймфрейме (по умолчанию 5 минут) ищем свечу-кульминацию:  
        - объем текущей свечи значительно превышает среднее,
        - тело свечи мало относительно всего диапазона (pin-bar), что
          свидетельствует о борьбе между покупателями и продавцами,
        - направление pin-bar противоположно предыдущему импульсу.
      * На старшем таймфрейме (по умолчанию 1 час) строится EMA.  
        Цена относительно этой EMA определяет контекст: если закрытие
        выше EMA, рынок рассматривается как бычий; если ниже - как
        медвежий.
      * Если появляется кульминационный pin-bar в контексте, противоположном
        текущему движению (например, медвежий pin-bar после роста),
        открываем разворотную сделку.  
      * Stop-loss размещается за экстремумом последнего бара с учетом ATR,
        take-profit - на EMA старшего таймфрейма, либо по фиксированному
        соотношению риск/прибыль, если EMA оказывается слишком близка или
        не обеспечивает адекватную цель.
      * Выход из позиции происходит при достижении цели (EMA или расстояние
        risk_reward * ATR) или по противоположному сигналу.

    Параметры
    ----------
    fast_tf : str
        Быстрый таймфрейм для поиска кульминации (например, '5m').
    slow_tf : str
        Медленный таймфрейм для оценки направления (например, '1h').
    ema_slow_period : int
        Период EMA на старшем таймфрейме, служащей ориентиром для take‑profit.
    vol_multiplier : float
        Множитель среднего объёма; если текущий объём превышает
        vol_multiplier * средний объём, свеча считается кульминационной.
    body_to_range_max : float
        Максимальная доля тела свечи от её полного диапазона, чтобы
        классифицировать бар как pin‑bar (например, 0.3 = тело ≤ 30% диапазона).
    atr_period : int
        Период для расчёта ATR на быстром таймфрейме.
    risk_reward : float
        Соотношение риск/прибыль для расчёта цели, если уровень EMA
        находится слишком близко или далёк.
    price_step : float
        Шаг округления цены (используется в некоторых биржах для корректного
        указания цен).
    
    Пример использования
    --------------------
    >>> strategy = StrategyVolumeClimaxReversal()
    >>> signal = strategy.execute(all_market_data, state)
    >>> if signal and signal['signal'] == 'BUY':
    ...     # открыть длинную позицию
    ...     pass
    """

    def __init__(self,
                 fast_tf: str = '5m',
                 slow_tf: str = '1h',
                 ema_slow_period: int = 20,
                 vol_multiplier: float = 3.0,
                 body_to_range_max: float = 0.3,
                 atr_period: int = 14,
                 risk_reward: float = 2.0,
                 price_step: float = 0.1):
        self.fast_tf = fast_tf
        self.slow_tf = slow_tf
        self.ema_slow_period = ema_slow_period
        self.vol_multiplier = vol_multiplier
        self.body_to_range_max = body_to_range_max
        self.atr_period = atr_period
        self.risk_reward = risk_reward
        self.price_step = price_step

    # --- Вспомогательные методы ---
    def round_price(self, price: float) -> float:
        """Округляет цену до ближайшего допустимого шага."""
        return round(price / self.price_step) * self.price_step

    def calculate_atr(self, df: pd.DataFrame) -> float:
        """Возвращает последнее значение ATR (Average True Range)."""
        high = df['high']
        low = df['low']
        close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr_series = tr.rolling(self.atr_period).mean()
        # fallback: если недостаточно данных, берём диапазон последней свечи
        return atr_series.iloc[-1] if not np.isnan(atr_series.iloc[-1]) else (high.iloc[-1] - low.iloc[-1])

    def is_pin_bar(self, df: pd.DataFrame) -> tuple:
        """
        Определяет, является ли последняя свеча pin‑bar.
        Условия: тело свечи ≤ body_to_range_max * диапазона.
        Возвращает tuple `(flag, direction)`, где flag — булево
        значение, direction — 'bull' для бычьего pin‑bar, 'bear' для
        медвежьего, None если не классифицирован.
        """
        open_price = df['open'].iloc[-1]
        close_price = df['close'].iloc[-1]
        high_price = df['high'].iloc[-1]
        low_price = df['low'].iloc[-1]
        total_range = high_price - low_price
        if total_range <= 0:
            return False, None
        body = abs(close_price - open_price)
        body_ratio = body / total_range
        if body_ratio <= self.body_to_range_max:
            direction = 'bull' if close_price > open_price else 'bear'
            return True, direction
        return False, None

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
        """
        Основной метод, вызываемый роботом. Принимает:

        * all_market_data: dict, где ключи — таймфреймы (строки),
          а значения — соответствующие DataFrame с колонками ['open','high','low','close','volume'].  
        * state: объект, содержащий атрибут `position` ('LONG'/'SHORT'/None) и
          опционально другие параметры (entry_price).  
        * bybit_api: объект клиента, у которого есть метод log_signal для
          записи сигналов (необязательно).  
        * symbol: торговый инструмент, по которому формируется сигнал.

        Возвращает словарь с полем `signal` ('BUY', 'SELL', 'EXIT_LONG', 'EXIT_SHORT')
        и дополнительной информацией, либо None, если сигнала нет.
        """
        # Получаем данные по таймфреймам
        df_fast = all_market_data.get(self.fast_tf)
        df_slow = all_market_data.get(self.slow_tf)
        if df_fast is None or df_slow is None:
            return None
        # Убедимся, что достаточно данных для ATR, EMA и оценки объёма
        min_len = max(self.atr_period, self.ema_slow_period, 20)
        if len(df_fast) < min_len or len(df_slow) < self.ema_slow_period:
            return None

        # Последние цены и объёмы
        latest_price = df_fast['close'].iloc[-1]
        current_vol = df_fast['volume'].iloc[-1]

        # EMA на старшем таймфрейме
        df_slow['ema_slow'] = df_slow['close'].ewm(span=self.ema_slow_period, adjust=False).mean()
        ema_target = df_slow['ema_slow'].iloc[-1]

        # ATR на быстром таймфрейме
        atr = self.calculate_atr(df_fast)

        # Средний объём и проверка всплеска
        vol_ma = df_fast['volume'].rolling(self.ema_slow_period).mean().iloc[-1]
        volume_climax = current_vol > self.vol_multiplier * vol_ma if not np.isnan(vol_ma) else False

        # Проверка pin‑bar и направление
        pin_flag, pin_direction = self.is_pin_bar(df_fast)

        # Проверка на открытую позицию
        in_position = self.is_in_position(state)
        position_side = getattr(state, 'position_side', None) if state is not None else None

        # Условия для входа
        long_signal = (not in_position and pin_direction == 'bullish' and 
                      current_vol > self.vol_multiplier * vol_ma and 
                      latest_price > ema_target)
        short_signal = (not in_position and pin_direction == 'bearish' and 
                       current_vol > self.vol_multiplier * vol_ma and 
                       latest_price < ema_target)

        # Условия для выхода
        exit_long = False
        exit_short = False
        if in_position:
            entry_price = getattr(state, 'entry_price', latest_price)
            # Цель для выхода: EMA или фиксированный RR
            if position_side == 'BUY':
                rr_target = entry_price + self.risk_reward * atr
                # Если цена достигла EMA старшего ТФ или RR‑цели — выходим
                if latest_price >= ema_target or latest_price >= rr_target:
                    exit_long = True
            elif position_side == 'SELL':
                rr_target = entry_price - self.risk_reward * atr
                if latest_price <= ema_target or latest_price <= rr_target:
                    exit_short = True

        # --- Формирование сигналов ---
        timestamp = df_fast.index[-1].isoformat() if hasattr(df_fast.index[-1], 'isoformat') else str(df_fast.index[-1])

        if long_signal:
            entry = self.round_price(latest_price)
            # Стоп: ниже минимума последнего бара минус ATR
            stop_loss = self.round_price(df_fast['low'].iloc[-1] - atr)
            # Цель: EMA или RR; выбираем вариант, который находится выше входа
            target = ema_target
            if target <= entry:
                target = entry + self.risk_reward * atr
            target = self.round_price(target)
            signal = {
                'symbol': symbol,
                'signal': 'BUY',
                'entry_price': entry,
                'stop_loss': stop_loss,
                'take_profit': target,
                'timestamp': timestamp,
                'strategy': 'VolumeClimaxReversal',
                'params': self.__dict__,
                'indicators': {
                    'ema_slow': ema_target,
                    'atr': atr,
                    'vol_ma': vol_ma,
                    'current_vol': current_vol,
                    'pin_bar': pin_direction,
                },
                'comment': 'Разворот вверх после кульминации объёма'
            }
            if bybit_api:
                # Логируем сигнал через API, если доступно
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
            entry = self.round_price(latest_price)
            # Стоп: выше максимума последнего бара плюс ATR
            stop_loss = self.round_price(df_fast['high'].iloc[-1] + atr)
            target = ema_target
            if target >= entry:
                target = entry - self.risk_reward * atr
            target = self.round_price(target)
            signal = {
                'symbol': symbol,
                'signal': 'SELL',
                'entry_price': entry,
                'stop_loss': stop_loss,
                'take_profit': target,
                'timestamp': timestamp,
                'strategy': 'VolumeClimaxReversal',
                'params': self.__dict__,
                'indicators': {
                    'ema_slow': ema_target,
                    'atr': atr,
                    'vol_ma': vol_ma,
                    'current_vol': current_vol,
                    'pin_bar': pin_direction,
                },
                'comment': 'Разворот вниз после кульминации объёма'
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
            return {'signal': 'EXIT_LONG', 'comment': 'Фиксация прибыли: достижение цели или EMA', 'timestamp': timestamp}
        elif exit_short:
            return {'signal': 'EXIT_SHORT', 'comment': 'Фиксация прибыли: достижение цели или EMA', 'timestamp': timestamp}

        return None