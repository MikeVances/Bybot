# bot/strategy/base/trailing_stop_mixin.py
"""
Универсальный миксин для trailing stop логики
Устраняет дублирование кода между стратегиями
"""

from __future__ import annotations

from typing import Dict, Any, Optional
import pandas as pd
from ..utils.indicators import TechnicalIndicators
from .enums import SignalType


class TrailingStopMixin:
    """
    Миксин для унификации trailing stop логики между стратегиями.

    Устраняет дублирование 60+ строк кода в CumDelta, MultiTF и VolumeVWAP стратегиях.
    """

    def calculate_trailing_stop_exit(
        self,
        market_data,
        state,
        current_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Унифицированная логика trailing stop для всех стратегий.

        Args:
            market_data: Рыночные данные (DataFrame или Dict[str, DataFrame])
            state: Состояние позиции
            current_price: Текущая цена

        Returns:
            Dict с сигналом выхода или None
        """

        # Валидация входных параметров
        if not self._should_apply_trailing_stop(state, current_price):
            return None

        position_side = getattr(state, 'position_side', None)
        entry_price = getattr(state, 'entry_price', None)

        if not position_side or entry_price is None:
            return None

        # Расчет PnL в процентах
        pnl_pct = self._calculate_pnl_pct(position_side, entry_price, current_price)

        # Проверка активации trailing stop
        if pnl_pct <= self.config.trailing_stop_activation_pct:
            return None

        # Расчет trailing distance на основе ATR
        trailing_distance = self._calculate_trailing_distance(market_data, entry_price)

        # Проверка условий срабатывания trailing stop
        return self._check_trailing_stop_conditions(
            position_side, current_price, trailing_distance, pnl_pct
        )

    def _should_apply_trailing_stop(self, state, current_price: float) -> bool:
        """Проверка базовых условий для применения trailing stop."""
        if not state or not hasattr(state, 'in_position'):
            return False

        if not getattr(state, 'in_position', False):
            return False

        if current_price <= 0:
            return False

        # Проверка наличия необходимого конфига
        if not hasattr(self.config, 'trailing_stop_activation_pct'):
            return False

        return True

    def _calculate_pnl_pct(self, position_side: str, entry_price: float, current_price: float) -> float:
        """Расчет PnL в процентах для любой стороны позиции."""
        if position_side in ['BUY', 'LONG']:
            return (current_price - entry_price) / entry_price * 100
        else:  # SELL, SHORT
            return (entry_price - current_price) / entry_price * 100

    def _calculate_trailing_distance(self, market_data, entry_price: float) -> float:
        """
        Расчет trailing distance на основе ATR.

        Поддерживает как DataFrame, так и Dict[str, DataFrame] для мультитаймфрейм стратегий.
        """
        try:
            # Получение DataFrame для расчета ATR
            df = self._extract_dataframe_for_atr(market_data)
            if df is None:
                return entry_price * 0.01  # Fallback: 1% от цены входа

            # Расчет ATR
            atr_result = TechnicalIndicators.calculate_atr_safe(df, 14)
            atr = atr_result.value if atr_result and atr_result.is_valid else entry_price * 0.01

            # Стандартный множитель ATR для trailing stop
            atr_multiplier = getattr(self.config, 'trailing_stop_atr_multiplier', 0.7)
            return atr * atr_multiplier

        except Exception as exc:
            self.logger.warning(f"Ошибка расчета trailing distance: {exc}")
            return entry_price * 0.01

    def _extract_dataframe_for_atr(self, market_data) -> Optional[pd.DataFrame]:
        """Извлечение DataFrame для расчета ATR из разных типов market_data."""

        # Случай 1: market_data уже DataFrame
        if isinstance(market_data, pd.DataFrame):
            return market_data

        # Случай 2: Dict с мультитаймфреймами
        if isinstance(market_data, dict):
            # Для MultiTF стратегий используем быстрый таймфрейм
            if hasattr(self.config, 'fast_tf'):
                df = market_data.get(self.config.fast_tf.value)
                if df is not None:
                    return df

            # Попытка получить через метод get_primary_dataframe
            if hasattr(self, 'get_primary_dataframe'):
                return self.get_primary_dataframe(market_data)

            # Fallback: первый доступный DataFrame
            for key, value in market_data.items():
                if isinstance(value, pd.DataFrame) and not value.empty:
                    return value

        return None

    def _check_trailing_stop_conditions(
        self,
        position_side: str,
        current_price: float,
        trailing_distance: float,
        pnl_pct: float
    ) -> Optional[Dict[str, Any]]:
        """Проверка условий срабатывания trailing stop."""

        if position_side in ['BUY', 'LONG']:
            trailing_stop = current_price - trailing_distance
            if current_price < trailing_stop:
                return {
                    'signal': SignalType.EXIT_LONG,
                    'reason': 'trailing_stop',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                    'trailing_stop_level': trailing_stop,
                    'trailing_distance': trailing_distance,
                }

        elif position_side in ['SELL', 'SHORT']:
            trailing_stop = current_price + trailing_distance
            if current_price > trailing_stop:
                return {
                    'signal': SignalType.EXIT_SHORT,
                    'reason': 'trailing_stop',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                    'trailing_stop_level': trailing_stop,
                    'trailing_distance': trailing_distance,
                }

        return None

    def get_trailing_stop_info(self, market_data, state, current_price: float) -> Dict[str, Any]:
        """
        Информация о текущем состоянии trailing stop (для отладки и мониторинга).

        Returns:
            Dict с информацией о trailing stop
        """
        if not self._should_apply_trailing_stop(state, current_price):
            return {'active': False, 'reason': 'conditions_not_met'}

        position_side = getattr(state, 'position_side', None)
        entry_price = getattr(state, 'entry_price', None)

        if not position_side or entry_price is None:
            return {'active': False, 'reason': 'missing_position_info'}

        pnl_pct = self._calculate_pnl_pct(position_side, entry_price, current_price)
        trailing_distance = self._calculate_trailing_distance(market_data, entry_price)

        activation_threshold = self.config.trailing_stop_activation_pct
        is_activated = pnl_pct > activation_threshold

        info = {
            'active': is_activated,
            'pnl_pct': pnl_pct,
            'activation_threshold': activation_threshold,
            'trailing_distance': trailing_distance,
            'position_side': position_side,
            'entry_price': entry_price,
            'current_price': current_price,
        }

        if is_activated:
            if position_side in ['BUY', 'LONG']:
                info['trailing_stop_level'] = current_price - trailing_distance
            else:
                info['trailing_stop_level'] = current_price + trailing_distance

        return info


# =========================================================================
# КОНФИГУРАЦИОННЫЕ РАСШИРЕНИЯ
# =========================================================================

class TrailingStopConfig:
    """Базовые параметры trailing stop для добавления в конфигурации стратегий."""

    trailing_stop_activation_pct: float = 3.0  # Активация при +3% прибыли
    trailing_stop_atr_multiplier: float = 0.7  # Дистанция = ATR * 0.7
    trailing_stop_enabled: bool = True  # Включен ли trailing stop