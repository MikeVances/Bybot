# bot/strategy/utils/exit_conditions.py
"""
Централизованный калькулятор условий выхода из позиций
Устраняет дублирование логики _check_strategic_exit_conditions между стратегиями
"""

from __future__ import annotations

from typing import Dict, Any, Optional, Callable
import pandas as pd
from ..base.enums import SignalType, PositionSide
from ..pipeline.common import StrategyIndicators


class ExitConditionsCalculator:
    """
    Централизованный калькулятор стратегических условий выхода.

    Унифицирует логику выхода между всеми стратегиями и устраняет дублирование.
    """

    # Реестр стратегии-специфичных обработчиков
    _strategy_exit_handlers: Dict[str, Callable] = {}

    @classmethod
    def register_strategy_handler(cls, strategy_type: str, handler: Callable) -> None:
        """Регистрация специфичного обработчика для стратегии."""
        cls._strategy_exit_handlers[strategy_type] = handler

    @classmethod
    def calculate_strategic_exit(
        cls,
        strategy_instance,
        market_data,
        state,
        current_price: float,
        indicators: Optional[StrategyIndicators] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Главный диспетчер для расчета стратегических выходов.

        Args:
            strategy_instance: Экземпляр стратегии
            market_data: Рыночные данные
            state: Состояние позиции
            current_price: Текущая цена
            indicators: Рассчитанные индикаторы

        Returns:
            Dict с сигналом выхода или None
        """

        # Базовая валидация
        if not cls._validate_exit_params(state, current_price):
            return None

        # 1. Проверка Trailing Stop (общая для всех стратегий)
        if hasattr(strategy_instance, 'calculate_trailing_stop_exit'):
            trailing_exit = strategy_instance.calculate_trailing_stop_exit(
                market_data, state, current_price
            )
            if trailing_exit:
                return trailing_exit

        # 2. Получение индикаторов если не переданы
        if indicators is None:
            indicators_dict = strategy_instance.calculate_strategy_indicators(market_data)
            if not indicators_dict:
                return None
            indicators = strategy_instance._ensure_bundle(indicators_dict)

        # 3. Проверка стратегии-специфичных условий выхода
        strategy_type = getattr(strategy_instance, 'strategy_type', strategy_instance.__class__.__name__.lower())
        return cls._check_strategy_specific_exits(
            strategy_type, strategy_instance, market_data, state, current_price, indicators
        )

    @classmethod
    def _validate_exit_params(cls, state, current_price: float) -> bool:
        """Базовая валидация параметров для выхода."""
        if not state or not hasattr(state, 'in_position'):
            return False

        if not getattr(state, 'in_position', False):
            return False

        if current_price <= 0:
            return False

        position_side = getattr(state, 'position_side', None)
        entry_price = getattr(state, 'entry_price', None)

        if not position_side or entry_price is None:
            return False

        return True

    @classmethod
    def _check_strategy_specific_exits(
        cls,
        strategy_type: str,
        strategy_instance,
        market_data,
        state,
        current_price: float,
        indicators: StrategyIndicators
    ) -> Optional[Dict[str, Any]]:
        """Проверка стратегии-специфичных условий выхода."""

        # Маппинг стратегий на методы проверки
        exit_checkers = {
            'volume_vwap': cls._check_vwap_exits,
            'cumdelta_sr': cls._check_cumdelta_exits,
            'multitf_volume': cls._check_multitf_exits,
            'fibonacci_rsi': cls._check_fibonacci_exits,
            'range_trading': cls._check_range_exits,
        }

        # Нормализация имени стратегии
        normalized_strategy = strategy_type.lower().replace('strategy', '').replace('_v3', '').replace('_v2', '').replace('_v1', '')

        checker = exit_checkers.get(normalized_strategy)
        if checker:
            return checker(strategy_instance, market_data, state, current_price, indicators)

        # Fallback: попытка использования зарегистрированного обработчика
        handler = cls._strategy_exit_handlers.get(strategy_type)
        if handler:
            return handler(strategy_instance, market_data, state, current_price, indicators)

        return None

    @classmethod
    def _check_vwap_exits(
        cls,
        strategy_instance,
        market_data,
        state,
        current_price: float,
        indicators: StrategyIndicators
    ) -> Optional[Dict[str, Any]]:
        """Специфичные условия выхода для Volume VWAP стратегии."""

        position_info = strategy_instance.get_position_info(state)
        position_side = position_info.get('side')

        # Выход для лонгов: цена ниже VWAP + подтверждение
        if position_side in ['BUY', PositionSide.LONG]:
            price_below_vwap = indicators.latest('price_below_vwap', False)
            volume_spike = indicators.latest('volume_spike', False)
            trend_bearish = indicators.latest('trend_bearish', False)

            if price_below_vwap and (volume_spike or trend_bearish):
                return {
                    'signal': SignalType.EXIT_LONG,
                    'exit_reason': 'vwap_reversal',
                    'current_price': current_price,
                    'comment': 'Выход: цена ниже VWAP с подтверждением',
                    'confluence': [
                        'price_below_vwap' if price_below_vwap else None,
                        'volume_spike' if volume_spike else None,
                        'trend_bearish' if trend_bearish else None,
                    ]
                }

        # Выход для шортов: цена выше VWAP + подтверждение
        if position_side in ['SELL', PositionSide.SHORT]:
            price_above_vwap = indicators.latest('price_above_vwap', False)
            volume_spike = indicators.latest('volume_spike', False)
            trend_bullish = indicators.latest('trend_bullish', False)

            if price_above_vwap and (volume_spike or trend_bullish):
                return {
                    'signal': SignalType.EXIT_SHORT,
                    'exit_reason': 'vwap_reversal',
                    'current_price': current_price,
                    'comment': 'Выход: цена выше VWAP с подтверждением',
                    'confluence': [
                        'price_above_vwap' if price_above_vwap else None,
                        'volume_spike' if volume_spike else None,
                        'trend_bullish' if trend_bullish else None,
                    ]
                }

        return None

    @classmethod
    def _check_cumdelta_exits(
        cls,
        strategy_instance,
        market_data,
        state,
        current_price: float,
        indicators: StrategyIndicators
    ) -> Optional[Dict[str, Any]]:
        """Специфичные условия выхода для CumDelta SR стратегии."""

        position_side = getattr(state, 'position_side', None)
        entry_price = getattr(state, 'entry_price', None)

        # Расчет PnL для контекста
        if position_side == 'BUY':
            pnl_pct = (current_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - current_price) / entry_price * 100

        cum_delta = indicators.latest('cum_delta', 0.0)

        # Выход для лонгов: негативная дельта
        if position_side == 'BUY' and cum_delta < -strategy_instance.config.min_delta_threshold:
            return {
                'signal': SignalType.EXIT_LONG,
                'reason': 'negative_delta',
                'current_price': current_price,
                'pnl_pct': pnl_pct,
                'cum_delta': cum_delta,
                'delta_threshold': -strategy_instance.config.min_delta_threshold,
            }

        # Выход для шортов: позитивная дельта
        if position_side == 'SELL' and cum_delta > strategy_instance.config.min_delta_threshold:
            return {
                'signal': SignalType.EXIT_SHORT,
                'reason': 'positive_delta',
                'current_price': current_price,
                'pnl_pct': pnl_pct,
                'cum_delta': cum_delta,
                'delta_threshold': strategy_instance.config.min_delta_threshold,
            }

        return None

    @classmethod
    def _check_multitf_exits(
        cls,
        strategy_instance,
        market_data,
        state,
        current_price: float,
        indicators: StrategyIndicators
    ) -> Optional[Dict[str, Any]]:
        """Специфичные условия выхода для MultiTF Volume стратегии."""

        position_side = getattr(state, 'position_side', None)
        entry_price = getattr(state, 'entry_price', None)

        # Расчет PnL для контекста
        if position_side == 'BUY':
            pnl_pct = (current_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - current_price) / entry_price * 100

        alignment_bull = indicators.latest('trends_aligned_bullish', False)
        alignment_bear = indicators.latest('trends_aligned_bearish', False)

        # Выход для лонгов: нарушение восходящего выравнивания трендов
        if position_side == 'BUY' and alignment_bear:
            return {
                'signal': SignalType.EXIT_LONG,
                'reason': 'trend_alignment_broken',
                'current_price': current_price,
                'pnl_pct': pnl_pct,
                'alignment_status': 'bearish',
            }

        # Выход для шортов: нарушение нисходящего выравнивания трендов
        if position_side == 'SELL' and alignment_bull:
            return {
                'signal': SignalType.EXIT_SHORT,
                'reason': 'trend_alignment_broken',
                'current_price': current_price,
                'pnl_pct': pnl_pct,
                'alignment_status': 'bullish',
            }

        return None

    @classmethod
    def _check_fibonacci_exits(
        cls,
        strategy_instance,
        market_data,
        state,
        current_price: float,
        indicators: StrategyIndicators
    ) -> Optional[Dict[str, Any]]:
        """Специфичные условия выхода для Fibonacci RSI стратегии."""

        # Пока нет специфичных условий выхода для Fibonacci RSI
        # Полагается только на trailing stop
        return None

    @classmethod
    def _check_range_exits(
        cls,
        strategy_instance,
        market_data,
        state,
        current_price: float,
        indicators: StrategyIndicators
    ) -> Optional[Dict[str, Any]]:
        """Специфичные условия выхода для Range Trading стратегии."""

        # Range trading стратегия может использовать быстрые выходы
        # при нарушении диапазона или изменении волатильности

        # Пока нет специфичных условий выхода
        # Полагается на trailing stop с низкими порогами
        return None


# =========================================================================
# ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ
# =========================================================================

class ExitSignalBuilder:
    """Утилита для создания стандартизированных сигналов выхода."""

    @staticmethod
    def build_exit_signal(
        signal_type: SignalType,
        reason: str,
        current_price: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Создание стандартизированного сигнала выхода.

        Args:
            signal_type: Тип сигнала (EXIT_LONG/EXIT_SHORT)
            reason: Причина выхода
            current_price: Текущая цена
            **kwargs: Дополнительные параметры

        Returns:
            Стандартизированный dict сигнала
        """
        signal = {
            'signal': signal_type,
            'reason': reason,
            'current_price': current_price,
            'timestamp': pd.Timestamp.now(),
        }
        signal.update(kwargs)
        return signal


# =========================================================================
# ДЕКОРАТОР ДЛЯ АВТОМАТИЧЕСКОЙ ИНТЕГРАЦИИ
# =========================================================================

def with_unified_exit_conditions(strategy_type: str):
    """
    Декоратор для автоматической интеграции унифицированной логики выходов.

    Usage:
        @with_unified_exit_conditions('volume_vwap')
        class VolumeVWAPStrategy(BaseStrategy):
            pass
    """
    def decorator(cls):
        # Сохранение оригинального метода если есть
        original_method = getattr(cls, '_check_strategic_exit_conditions', None)

        def unified_exit_conditions(self, market_data, state, current_price: float):
            return ExitConditionsCalculator.calculate_strategic_exit(
                self, market_data, state, current_price
            )

        cls._check_strategic_exit_conditions = unified_exit_conditions
        cls.strategy_type = strategy_type

        # Сохранение ссылки на оригинальный метод для fallback
        if original_method:
            cls._original_exit_conditions = original_method

        return cls

    return decorator