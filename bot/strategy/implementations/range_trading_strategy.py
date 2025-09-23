# bot/strategy/implementations/range_trading_strategy.py
"""
Range Trading Strategy - стратегия для бокового рынка
Специально адаптирована для частых сделок с минимальным профитом
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import logging

from ..base import (
    BaseStrategy,
    VolumeVWAPConfig,
    MarketRegime,
    SignalType,
    ConfluenceFactor,
    PositionSide,
)
from ..utils.validators import DataValidator
from ..utils.market_analysis import MarketRegimeAnalyzer
from ..pipeline.common import StrategyIndicators, SignalDecision, PositionPlan
from ..modules.range_pipeline import RangeIndicatorEngine, RangeSignalGenerator, RangePositionSizer


class RangeTradingStrategy(BaseStrategy):
    """
    Range Trading Strategy v1.0
    
    Специальная стратегия для бокового рынка:
    - Частые сделки с минимальным профитом
    - Низкие требования к объему
    - Фокус на краткосрочных движениях
    - Адаптивные SL/TP для диапазона
    """
    
    def __init__(self, config: VolumeVWAPConfig):
        """
        Инициализация Range Trading стратегии
        
        Args:
            config: Конфигурация стратегии
        """
        super().__init__(config, "RangeTrading_v1")
        
        # Специфичная конфигурация для диапазона
        self.config: VolumeVWAPConfig = config

        # Адаптируем параметры для бокового рынка
        self.config.volume_multiplier = 1.2  # Низкий порог объема
        self.config.signal_strength_threshold = 0.3  # Низкий порог силы сигнала
        self.config.confluence_required = 1  # Минимум подтверждений
        self.config.risk_reward_ratio = 1.2  # Низкий R:R для частых сделок
        self.config.min_risk_reward_ratio = 0.8  # Снижаем минимальное R:R для диапазона

        self.indicator_engine = RangeIndicatorEngine(self.config, base_indicator_fn=self.calculate_base_indicators)
        self.signal_generator = RangeSignalGenerator(self.config)
        self.position_sizer = RangePositionSizer(self.config, round_price_fn=self.round_price)
        self._last_indicator_bundle: Optional[StrategyIndicators] = None

        self.logger.info("🎯 Range Trading стратегия инициализирована")
        self.logger.info(
            "📊 Параметры: volume_mult=%s, signal_strength=%s",
            self.config.volume_multiplier,
            self.config.signal_strength_threshold,
        )
    
    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        """
        Расчет индикаторов для Range Trading стратегии

        Args:
            market_data: Рыночные данные

        Returns:
            Dict с рассчитанными индикаторами
        """
        try:
            df = self.get_primary_dataframe(market_data)
            if df is None:
                self.logger.error("Не удалось получить данные для расчета индикаторов")
                return {}

            bundle = self.indicator_engine.calculate(df)
            self._last_indicator_bundle = bundle
            self.logger.debug(
                "Рассчитано %s индикаторов для Range Trading стратегии",
                len(bundle.data),
            )
            return bundle.data

        except Exception as e:
            self.logger.error(f"Ошибка расчета индикаторов Range Trading стратегии: {e}")
            return {}

    def calculate_signal_strength(self, market_data, indicators: Dict, signal_type: str) -> float:
        """
        Расчет силы сигнала для Range Trading стратегии
        """
        try:
            bundle = self._bundle_from_dict(indicators)
            return self.signal_generator.calculate_strength(bundle, signal_type)
        except Exception as e:
            self.logger.error(f"Ошибка расчета силы сигнала: {e}")
            return 0.0

    def check_confluence_factors(self, market_data, indicators: Dict, signal_type: str) -> Tuple[int, List[str]]:
        """
        Проверка confluence факторов для Range Trading стратегии
        """
        try:
            bundle = self._bundle_from_dict(indicators)
            factors = self.signal_generator.confluence_factors(bundle, signal_type)
            return len(factors), factors
        except Exception as e:
            self.logger.error(f"Ошибка проверки confluence факторов: {e}")
            return 0, []

    def execute(self, market_data, state=None, bybit_api=None, symbol='BTCUSDT') -> Optional[Dict]:
        """
        Основная логика выполнения Range Trading стратегии
        """
        signal_result: Optional[Dict] = None
        try:
            can_execute, reason = self.pre_execution_check(market_data, state)
            if not can_execute:
                self.logger.debug(f"Выполнение отменено: {reason}")
                return None

            df = self.get_primary_dataframe(market_data)
            if df is None:
                self.logger.error("Не удалось получить данные для выполнения стратегии")
                return None

            self._execution_count += 1

            market_analysis = self.analyze_current_market(df)
            condition = market_analysis.get('condition')
            if condition and self._execution_count % 10 == 0:
                self.log_market_analysis(market_analysis)

            indicators_dict = self.calculate_strategy_indicators(market_data)
            if not indicators_dict:
                self.logger.error("Ошибка расчета индикаторов")
                return None
            indicator_bundle = self._last_indicator_bundle or StrategyIndicators(indicators_dict)

            current_price = df['close'].iloc[-1]

            if self.is_in_position(state):
                exit_signal = self.should_exit_position(market_data, state, current_price)
                if exit_signal:
                    self.logger.info(f"🚪 Генерация сигнала выхода: {exit_signal.get('signal')}")
                    return exit_signal
                return None

            if self._execution_count % 5 == 0:
                volume_ratio = indicator_bundle.latest('volume_ratio', 0.0)
                rsi = indicator_bundle.latest('rsi', 50.0)
                momentum = indicator_bundle.latest('price_momentum', 0.0)
                self.logger.info(
                    "🔍 Range Trading отладка: vol_ratio=%s, rsi=%s, momentum=%s",
                    f"{volume_ratio:.2f}",
                    f"{rsi:.1f}",
                    f"{momentum:.4f}",
                )

            decision = self.signal_generator.generate(
                df=df,
                indicators=indicator_bundle,
                current_price=current_price,
                market_analysis=market_analysis,
            )
            if not decision.is_actionable:
                return None

            plan = self.position_sizer.plan(decision, df, current_price)
            if not plan.is_ready:
                reason = plan.metadata.get('reject_reason', 'position plan invalid')
                self.logger.debug(f"📉 План позиции отклонен: {reason}")
                return None

            signal_result = self._build_signal(symbol, decision, plan)
            self._log_signal(bybit_api, signal_result, decision)
            self.log_signal_generation(signal_result, {
                'market_analysis': market_analysis,
                'position_plan': plan.metadata,
            })
            return signal_result

        except Exception as e:
            self.logger.error(f"Критическая ошибка выполнения Range Trading стратегии: {e}", exc_info=True)
            return None

        finally:
            self.post_execution_tasks(signal_result, market_data, state)


    def _bundle_from_dict(self, indicators: Dict[str, Any]) -> StrategyIndicators:
        if isinstance(indicators, StrategyIndicators):
            return indicators
        return StrategyIndicators(data=indicators)

    def _build_signal(self, symbol: str, decision: SignalDecision, plan: PositionPlan) -> Dict[str, Any]:
        indicators_snapshot = decision.context.get('indicators', {})
        additional_data = {
            'trade_amount': plan.size,
            'position_plan': plan.metadata,
        }
        return self.create_signal(
            signal_type=decision.signal,
            entry_price=plan.entry_price,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            indicators=indicators_snapshot,
            confluence_factors=decision.confluence,
            signal_strength=decision.confidence,
            symbol=symbol,
            additional_data=additional_data,
        )

    def _log_signal(self, bybit_api, signal: Dict[str, Any], decision: SignalDecision) -> None:
        if not bybit_api:
            return
        try:
            bybit_api.log_strategy_signal(
                strategy=signal['strategy'],
                symbol=signal['symbol'],
                signal=signal['signal'],
                market_data=signal['indicators'],
                indicators=signal['indicators'],
                comment=f"Range Trading: {', '.join(decision.confluence)}"
            )
        except Exception as api_error:
            self.logger.error(f"Ошибка логирования API: {api_error}")



# =========================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =========================================================================


def create_range_trading_strategy() -> RangeTradingStrategy:
    """Создание Range Trading стратегии"""
    config = VolumeVWAPConfig(
        volume_multiplier=1.2,
        signal_strength_threshold=0.3,
        confluence_required=1,
        risk_reward_ratio=1.2,
        max_risk_per_trade_pct=0.5,  # Низкий риск для частых сделок
        min_volume_for_signal=100  # Низкий объем
    )
    return RangeTradingStrategy(config)


# =========================================================================
# КОНСТАНТЫ И МЕТАДАННЫЕ
# =========================================================================

STRATEGY_INFO = {
    'name': 'Range_Trading',
    'version': '1.0.0',
    'description': 'Стратегия для бокового рынка с частыми сделками и минимальным профитом',
    'author': 'TradingBot Team',
    'category': 'Range Trading',
    'timeframes': ['1m', '5m', '15m'],
    'min_data_points': 50,
    'supported_assets': ['crypto', 'forex', 'stocks'],
    'market_conditions': ['sideways', 'range', 'low_volatility']
} 
