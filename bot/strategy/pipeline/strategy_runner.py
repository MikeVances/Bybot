"""Mixins for pipeline-backed strategies."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .common import (
    StrategyIndicators,
    StrategyPipeline,
    SignalDecision,
    PositionPlan,
)


class PipelineStrategyMixin:
    """Provides default implementations for pipeline-driven strategies."""

    pipeline: StrategyPipeline
    signal_generator: Any
    position_sizer: Any

    def _init_pipeline(self, pipeline: StrategyPipeline) -> None:
        self.pipeline = pipeline
        self.signal_generator = pipeline.signal_generator
        self.position_sizer = pipeline.position_sizer
        self._pipeline_indicators: Optional[StrategyIndicators] = None

    # ------------------------------------------------------------------
    # Indicator & signal helpers
    # ------------------------------------------------------------------

    def _ensure_bundle(self, indicators: Any) -> StrategyIndicators:
        if isinstance(indicators, StrategyIndicators):
            return indicators
        if self._pipeline_indicators is not None:
            return self._pipeline_indicators
        if isinstance(indicators, dict):
            return StrategyIndicators(data=indicators)
        return StrategyIndicators(data={})

    def _after_indicator_calculation(self, bundle: StrategyIndicators) -> None:
        """Hook for subclasses to react after indicators were computed."""
        # Default: no-op

    def calculate_strategy_indicators(self, market_data) -> Dict[str, Any]:
        df = self.get_primary_dataframe(market_data)
        if df is None:
            self.logger.error("Не удалось получить данные для расчетов индикаторов")
            self._pipeline_indicators = None
            return {}

        bundle = self.pipeline.indicator_engine.calculate(df)
        self._pipeline_indicators = bundle
        self._after_indicator_calculation(bundle)
        return bundle.data

    def calculate_signal_strength(self, market_data, indicators: Dict, signal_type: str) -> float:
        generator = getattr(self, "signal_generator", None)
        if not generator or not hasattr(generator, "calculate_strength"):
            return 0.0
        bundle = self._ensure_bundle(indicators)
        try:
            return float(generator.calculate_strength(bundle, signal_type))
        except Exception as exc:
            self.logger.error(f"Ошибка расчета силы сигнала: {exc}")
            return 0.0

    def check_confluence_factors(self, market_data, indicators: Dict, signal_type: str) -> Tuple[int, list[str]]:
        generator = getattr(self, "signal_generator", None)
        if not generator or not hasattr(generator, "confluence_factors"):
            return 0, []
        bundle = self._ensure_bundle(indicators)
        try:
            factors = generator.confluence_factors(bundle, signal_type)
            return len(factors), factors
        except Exception as exc:
            self.logger.error(f"Ошибка расчета confluence факторов: {exc}")
            return 0, []

    # ------------------------------------------------------------------
    # Execution flow
    # ------------------------------------------------------------------

    def _on_market_analysis(self, market_analysis: Dict[str, Any], df: pd.DataFrame) -> None:
        """Hook after market analysis is computed."""
        # Default: no-op

    def _before_signal_generation(
        self,
        df: pd.DataFrame,
        indicators: StrategyIndicators,
        market_analysis: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Hook to apply additional filters before generating signals."""
        return True, None

    def _after_signal_generated(
        self,
        decision: SignalDecision,
        plan: PositionPlan,
        indicators: StrategyIndicators,
        market_analysis: Dict[str, Any],
    ) -> None:
        """Hook executed after signal has been accepted."""
        # Default: no-op

    def _build_signal_from_plan(
        self,
        symbol: str,
        decision: SignalDecision,
        plan: PositionPlan,
    ) -> Dict[str, Any]:
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
                market_data=signal.get('indicators', {}),
                indicators=signal.get('indicators', {}),
                comment=', '.join(decision.confluence),
            )
        except Exception as api_error:
            self.logger.error(f"Ошибка логирования сигнала в API: {api_error}")

    def execute(self, market_data, state=None, bybit_api=None, symbol='BTCUSDT') -> Optional[Dict[str, Any]]:
        signal_result: Optional[Dict[str, Any]] = None
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
            self._on_market_analysis(market_analysis, df)

            indicators_dict = self.calculate_strategy_indicators(market_data)
            if not indicators_dict:
                return None
            indicator_bundle = self._ensure_bundle(indicators_dict)

            current_price = df['close'].iloc[-1]

            if self.is_in_position(state):
                exit_signal = self.should_exit_position(market_data, state, current_price)
                if exit_signal:
                    self.logger.info(f"🚪 Генерация сигнала выхода: {exit_signal.get('signal')}")
                    return exit_signal
                return None

            allowed, filter_reason = self._before_signal_generation(df, indicator_bundle, market_analysis)
            if not allowed:
                if filter_reason:
                    self.logger.debug(f"Сигнал отклонен фильтрами: {filter_reason}")
                return None

            decision = self.pipeline.signal_generator.generate(
                df=df,
                indicators=indicator_bundle,
                current_price=current_price,
                market_analysis=market_analysis,
            )
            if not decision.is_actionable:
                return None

            plan = self.pipeline.position_sizer.plan(decision, df, current_price)
            if not plan.is_ready:
                reject_reason = plan.metadata.get('reject_reason', 'position plan invalid')
                self.logger.debug(f"📉 План позиции отклонен: {reject_reason}")
                return None

            signal_result = self._build_signal_from_plan(symbol, decision, plan)
            self._log_signal(bybit_api, signal_result, decision)
            self.log_signal_generation(
                signal_result,
                {
                    'market_analysis': market_analysis,
                    'position_plan': plan.metadata,
                },
            )
            self._after_signal_generated(decision, plan, indicator_bundle, market_analysis)
            return signal_result

        except Exception as exc:
            self.logger.error(f"Критическая ошибка выполнения стратегии: {exc}", exc_info=True)
            return None
        finally:
            self.post_execution_tasks(signal_result, market_data, state)
