# bot/strategy/utils/market_analysis.py
"""
Система анализа рыночных режимов для адаптации торговых стратегий
Определяет текущее состояние рынка и рекомендует параметры
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from ..base.enums import MarketRegime, TimeFrame
from .indicators import TechnicalIndicators

# Настройка логирования
logger = logging.getLogger(__name__)


@dataclass
class MarketCondition:
    """Класс для представления рыночных условий"""
    regime: MarketRegime
    volatility: float  # Историческая волатильность
    trend_strength: float  # Сила тренда (0-1)
    trend_direction: int  # Направление тренда (-1, 0, 1)
    volume_activity: float  # Активность объема (относительно средней)
    momentum: float  # Моментум цены
    confidence: float  # Уверенность в определении режима (0-1)
    
    # Дополнительные метрики
    atr_normalized: float  # Нормализованный ATR
    range_efficiency: float  # Эффективность движения
    consolidation_factor: float  # Фактор консолидации
    breakout_potential: float  # Потенциал пробоя
    
    # Временные характеристики
    regime_duration: int  # Длительность текущего режима (в барах)
    stability: float  # Стабильность режима
    
    @property
    def is_trending(self) -> bool:
        """Проверка трендового состояния"""
        return self.regime in [MarketRegime.TRENDING] or self.trend_strength > 0.6
    
    @property
    def is_volatile(self) -> bool:
        """Проверка волатильного состояния"""
        return self.regime == MarketRegime.VOLATILE or self.volatility > 0.03
    
    @property
    def is_stable(self) -> bool:
        """Проверка стабильного состояния"""
        return self.regime in [MarketRegime.NORMAL, MarketRegime.SIDEWAYS]
    
    @property
    def is_bullish(self) -> bool:
        """Проверка бычьего настроения"""
        return self.trend_direction > 0 and self.momentum > 0
    
    @property
    def is_bearish(self) -> bool:
        """Проверка медвежьего настроения"""
        return self.trend_direction < 0 and self.momentum < 0
    
    def __str__(self) -> str:
        direction = "↗️" if self.is_bullish else "↘️" if self.is_bearish else "➡️"
        return f"{self.regime.value.title()} {direction} (trend: {self.trend_strength:.2f}, vol: {self.volatility:.3f})"


class MarketRegimeAnalyzer:
    """
    Основной класс для анализа рыночных режимов
    Определяет текущее состояние рынка на основе множественных факторов
    """
    
    @staticmethod
    def analyze_market_condition(df: pd.DataFrame, 
                                period: int = 50,
                                short_period: int = 20) -> MarketCondition:
        """
        Комплексный анализ рыночных условий
        
        Args:
            df: DataFrame с OHLCV данными
            period: Основной период для анализа
            short_period: Короткий период для быстрых индикаторов
        
        Returns:
            MarketCondition с полным анализом рынка
        """
        try:
            if len(df) < period:
                logger.warning(f"Недостаточно данных для анализа: {len(df)} < {period}")
                return MarketRegimeAnalyzer._get_default_condition()
            
            # 1. Анализ волатильности
            volatility_metrics = MarketRegimeAnalyzer._analyze_volatility(df, period)
            
            # 2. Анализ тренда
            trend_metrics = MarketRegimeAnalyzer._analyze_trend(df, period, short_period)
            
            # 3. Анализ объема
            volume_metrics = MarketRegimeAnalyzer._analyze_volume(df, period)
            
            # 4. Анализ моментума
            momentum_metrics = MarketRegimeAnalyzer._analyze_momentum(df, short_period)
            
            # 5. Анализ консолидации/пробоев
            structure_metrics = MarketRegimeAnalyzer._analyze_market_structure(df, period)
            
            # 6. Определение режима
            regime = MarketRegimeAnalyzer._determine_regime(
                volatility_metrics, trend_metrics, volume_metrics, 
                momentum_metrics, structure_metrics
            )
            
            # 7. Расчет уверенности
            confidence = MarketRegimeAnalyzer._calculate_confidence(
                volatility_metrics, trend_metrics, volume_metrics
            )
            
            # 8. Анализ стабильности режима
            stability_metrics = MarketRegimeAnalyzer._analyze_regime_stability(df, regime, period)
            
            return MarketCondition(
                regime=regime,
                volatility=volatility_metrics['historical_volatility'],
                trend_strength=trend_metrics['strength'],
                trend_direction=trend_metrics['direction'],
                volume_activity=volume_metrics['activity_ratio'],
                momentum=momentum_metrics['normalized_momentum'],
                confidence=confidence,
                atr_normalized=volatility_metrics['atr_normalized'],
                range_efficiency=trend_metrics['efficiency'],
                consolidation_factor=structure_metrics['consolidation_factor'],
                breakout_potential=structure_metrics['breakout_potential'],
                regime_duration=stability_metrics['duration'],
                stability=stability_metrics['stability']
            )
            
        except Exception as e:
            logger.error(f"Ошибка анализа рыночных условий: {e}")
            return MarketRegimeAnalyzer._get_default_condition()
    
    @staticmethod
    def _analyze_volatility(df: pd.DataFrame, period: int) -> Dict[str, float]:
        """Анализ волатильности рынка"""
        try:
            # Историческая волатильность
            returns = df['close'].pct_change().dropna()
            hist_vol = returns.tail(period).std()
            
            # ATR волатильность
            atr_result = TechnicalIndicators.calculate_atr_safe(df, min(period, 14))
            atr_vol = atr_result.value / df['close'].iloc[-1] if atr_result.is_valid else 0
            
            # Parkinson estimator (более эффективная оценка)
            if period <= len(df):
                log_hl_ratio = np.log(df['high'].tail(period) / df['low'].tail(period))
                parkinson_vol = np.sqrt((1 / (4 * np.log(2))) * (log_hl_ratio ** 2).mean())
            else:
                parkinson_vol = hist_vol
            
            # Волатильность волатильности
            vol_rolling = returns.rolling(10).std()
            vol_of_vol = vol_rolling.tail(period).std()
            
            # GARCH-подобная волатильность (упрощенная)
            alpha = 0.1
            garch_vol = hist_vol
            for ret in returns.tail(period):
                garch_vol = (1 - alpha) * garch_vol + alpha * (ret ** 2)
            garch_vol = np.sqrt(garch_vol)
            
            return {
                'historical_volatility': float(hist_vol),
                'atr_volatility': float(atr_vol),
                'parkinson_volatility': float(parkinson_vol),
                'vol_of_vol': float(vol_of_vol),
                'garch_volatility': float(garch_vol),
                'atr_normalized': float(atr_vol)
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа волатильности: {e}")
            return {
                'historical_volatility': 0.02,
                'atr_volatility': 0.01,
                'parkinson_volatility': 0.02,
                'vol_of_vol': 0.005,
                'garch_volatility': 0.02,
                'atr_normalized': 0.01
            }
    
    @staticmethod
    def _analyze_trend(df: pd.DataFrame, period: int, short_period: int) -> Dict[str, float]:
        """Анализ трендовых характеристик"""
        try:
            # Скользящие средние разных периодов
            sma_short = df['close'].rolling(short_period).mean()
            sma_long = df['close'].rolling(period).mean()
            ema_short = df['close'].ewm(span=short_period).mean()
            
            # Наклон тренда
            if len(sma_long.dropna()) > 0:
                slope = sma_long.diff(period // 4).iloc[-1] / df['close'].iloc[-1]
            else:
                slope = 0
            
            # Направление тренда
            if sma_short.iloc[-1] > sma_long.iloc[-1]:
                direction = 1  # Вверх
            elif sma_short.iloc[-1] < sma_long.iloc[-1]:
                direction = -1  # Вниз
            else:
                direction = 0  # Боковик
            
            # Сила тренда через R-squared
            x = np.arange(len(sma_long.dropna()))
            y = sma_long.dropna().values
            if len(x) >= 2 and len(y) >= 2:
                correlation = np.corrcoef(x, y)[0, 1]
                r_squared = correlation ** 2 if not np.isnan(correlation) else 0
            else:
                r_squared = 0
            
            # Эффективность движения (отношение прямого движения к сумме движений)
            price_changes = df['close'].diff().tail(period)
            total_movement = price_changes.abs().sum()
            net_movement = abs(price_changes.sum())
            efficiency = net_movement / total_movement if total_movement > 0 else 0
            
            # ADX-подобный индикатор (упрощенный)
            high_diff = df['high'].diff()
            low_diff = df['low'].diff()
            
            plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
            minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
            
            atr_series = TechnicalIndicators.calculate_atr_series(df, 14).value
            
            plus_di = pd.Series(plus_dm).rolling(14).sum() / atr_series.rolling(14).sum() * 100
            minus_di = pd.Series(minus_dm).rolling(14).sum() / atr_series.rolling(14).sum() * 100
            
            dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
            adx = dx.rolling(14).mean().iloc[-1] if len(dx) > 14 else 25
            
            # Нормализация силы тренда
            trend_strength = min(max(r_squared, 0), 1)
            
            return {
                'slope': float(slope),
                'direction': direction,
                'strength': float(trend_strength),
                'efficiency': float(efficiency),
                'adx': float(adx) if not pd.isna(adx) else 25.0,
                'sma_diff_pct': float((sma_short.iloc[-1] - sma_long.iloc[-1]) / sma_long.iloc[-1] * 100) if sma_long.iloc[-1] > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа тренда: {e}")
            return {
                'slope': 0.0,
                'direction': 0,
                'strength': 0.3,
                'efficiency': 0.5,
                'adx': 25.0,
                'sma_diff_pct': 0.0
            }
    
    @staticmethod
    def _analyze_volume(df: pd.DataFrame, period: int) -> Dict[str, float]:
        """Анализ объемных характеристик"""
        try:
            if 'volume' not in df.columns:
                return {
                    'activity_ratio': 1.0,
                    'trend_confirmation': 0.5,
                    'distribution': 0.0
                }
            
            # Средний объем
            avg_volume = df['volume'].tail(period).mean()
            current_volume = df['volume'].iloc[-1]
            
            # Коэффициент активности
            activity_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Подтверждение тренда объемом (OBV-подобное)
            price_changes = df['close'].pct_change()
            volume_direction = np.where(price_changes > 0, 1, np.where(price_changes < 0, -1, 0))
            volume_weighted = (volume_direction * df['volume']).tail(period)
            
            obv_trend = volume_weighted.sum()
            max_possible_obv = df['volume'].tail(period).sum()
            trend_confirmation = abs(obv_trend) / max_possible_obv if max_possible_obv > 0 else 0
            
            # Распределение объема (концентрация vs распределение)
            volume_std = df['volume'].tail(period).std()
            volume_mean = df['volume'].tail(period).mean()
            volume_cv = volume_std / volume_mean if volume_mean > 0 else 0  # Коэффициент вариации
            
            return {
                'activity_ratio': float(activity_ratio),
                'trend_confirmation': float(trend_confirmation),
                'distribution': float(volume_cv),
                'avg_volume': float(avg_volume),
                'volume_trend': float(obv_trend)
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа объема: {e}")
            return {
                'activity_ratio': 1.0,
                'trend_confirmation': 0.5,
                'distribution': 0.5,
                'avg_volume': 1000.0,
                'volume_trend': 0.0
            }
    
    @staticmethod
    def _analyze_momentum(df: pd.DataFrame, period: int) -> Dict[str, float]:
        """Анализ моментума рынка"""
        try:
            # Ценовой моментум разных периодов
            momentum_1 = df['close'].pct_change(1).iloc[-1]
            momentum_5 = df['close'].pct_change(5).iloc[-1]
            momentum_period = df['close'].pct_change(period).iloc[-1]
            
            # RSI для определения перекупленности/перепроданности
            rsi_result = TechnicalIndicators.calculate_rsi(df, 14)
            rsi = rsi_result.value.iloc[-1] if rsi_result.is_valid else 50
            
            # MACD для определения смены моментума
            macd_result = TechnicalIndicators.calculate_macd(df)
            if macd_result.is_valid:
                macd_line = macd_result.value['macd'].iloc[-1]
                signal_line = macd_result.value['signal'].iloc[-1]
                macd_histogram = macd_result.value['histogram'].iloc[-1]
                macd_signal = 1 if macd_line > signal_line else -1
            else:
                macd_histogram = 0
                macd_signal = 0
            
            # Нормализованный моментум (комбинированный)
            momentum_factors = [momentum_1, momentum_5, momentum_period]
            avg_momentum = np.mean(momentum_factors)
            
            # Ускорение (вторая производная)
            recent_changes = df['close'].pct_change().tail(5)
            acceleration = recent_changes.diff().mean()
            
            return {
                'momentum_1': float(momentum_1),
                'momentum_5': float(momentum_5),
                'momentum_period': float(momentum_period),
                'normalized_momentum': float(avg_momentum),
                'rsi': float(rsi),
                'macd_histogram': float(macd_histogram),
                'macd_signal': macd_signal,
                'acceleration': float(acceleration)
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа моментума: {e}")
            return {
                'momentum_1': 0.0,
                'momentum_5': 0.0,
                'momentum_period': 0.0,
                'normalized_momentum': 0.0,
                'rsi': 50.0,
                'macd_histogram': 0.0,
                'macd_signal': 0,
                'acceleration': 0.0
            }
    
    @staticmethod
    def _analyze_market_structure(df: pd.DataFrame, period: int) -> Dict[str, float]:
        """Анализ структуры рынка (консолидация vs пробои)"""
        try:
            # Анализ диапазонов
            recent_data = df.tail(period)
            high_range = recent_data['high'].max()
            low_range = recent_data['low'].min()
            current_price = df['close'].iloc[-1]
            
            # Фактор консолидации (насколько цена находится в диапазоне)
            range_size = high_range - low_range
            price_position = (current_price - low_range) / range_size if range_size > 0 else 0.5
            
            # Сжатие диапазона (Bollinger Bands squeeze)
            bb_result = TechnicalIndicators.calculate_bollinger_bands(df, 20)
            if bb_result.is_valid:
                bb_width = bb_result.value['width'].iloc[-1]
                bb_avg_width = bb_result.value['width'].tail(period).mean()
                squeeze_factor = bb_width / bb_avg_width if bb_avg_width > 0 else 1.0
            else:
                squeeze_factor = 1.0
            
            # Потенциал пробоя
            # Основан на сжатии волатильности и позиции в диапазоне
            volatility_squeeze = 1 - squeeze_factor if squeeze_factor < 1 else 0
            edge_proximity = min(price_position, 1 - price_position) * 2  # Близость к краям
            
            breakout_potential = (volatility_squeeze + (1 - edge_proximity)) / 2
            
            # Фактор консолидации
            price_range_pct = range_size / current_price if current_price > 0 else 0
            consolidation_factor = 1 - min(price_range_pct / 0.1, 1)  # Инвертируем - малый диапазон = высокая консолидация
            
            return {
                'consolidation_factor': float(consolidation_factor),
                'breakout_potential': float(breakout_potential),
                'price_position_in_range': float(price_position),
                'range_size_pct': float(price_range_pct),
                'squeeze_factor': float(squeeze_factor)
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа структуры рынка: {e}")
            return {
                'consolidation_factor': 0.5,
                'breakout_potential': 0.3,
                'price_position_in_range': 0.5,
                'range_size_pct': 0.05,
                'squeeze_factor': 1.0
            }
    
    @staticmethod
    def _determine_regime(volatility_metrics: Dict, trend_metrics: Dict, 
                         volume_metrics: Dict, momentum_metrics: Dict,
                         structure_metrics: Dict) -> MarketRegime:
        """Определение рыночного режима на основе всех метрик"""
        try:
            # Извлекаем ключевые метрики
            volatility = volatility_metrics['historical_volatility']
            trend_strength = trend_metrics['strength']
            trend_direction = trend_metrics['direction']
            volume_activity = volume_metrics['activity_ratio']
            momentum = abs(momentum_metrics['normalized_momentum'])
            consolidation = structure_metrics['consolidation_factor']
            
            # Пороги для классификации
            HIGH_VOL_THRESHOLD = 0.03
            TREND_THRESHOLD = 0.6
            HIGH_MOMENTUM_THRESHOLD = 0.02
            HIGH_VOLUME_THRESHOLD = 1.5
            CONSOLIDATION_THRESHOLD = 0.7
            
            # Логика определения режима
            
            # 1. Высокая волатильность
            if volatility > HIGH_VOL_THRESHOLD:
                return MarketRegime.VOLATILE
            
            # 2. Сильный тренд
            if trend_strength > TREND_THRESHOLD and momentum > HIGH_MOMENTUM_THRESHOLD:
                return MarketRegime.TRENDING
            
            # 3. Консолидация/боковик
            if consolidation > CONSOLIDATION_THRESHOLD or trend_strength < 0.3:
                return MarketRegime.SIDEWAYS
            
            # 4. Высокая объемная активность
            if volume_activity > HIGH_VOLUME_THRESHOLD and momentum > HIGH_MOMENTUM_THRESHOLD:
                return MarketRegime.HIGH_VOLUME
            
            # 5. Низкая активность
            if volume_activity < 0.5 and momentum < 0.005:
                return MarketRegime.LOW_VOLUME
            
            # 6. По умолчанию - нормальный режим
            return MarketRegime.NORMAL
            
        except Exception as e:
            logger.error(f"Ошибка определения режима: {e}")
            return MarketRegime.NORMAL
    
    @staticmethod
    def _calculate_confidence(volatility_metrics: Dict, trend_metrics: Dict, 
                            volume_metrics: Dict) -> float:
        """Расчет уверенности в определении режима"""
        try:
            confidence_factors = []
            
            # Фактор волатильности (стабильность определения)
            vol = volatility_metrics['historical_volatility']
            vol_of_vol = volatility_metrics['vol_of_vol']
            vol_confidence = 1 - min(vol_of_vol / vol, 1) if vol > 0 else 0.5
            confidence_factors.append(vol_confidence)
            
            # Фактор тренда (четкость направления)
            trend_strength = trend_metrics['strength']
            trend_confidence = trend_strength
            confidence_factors.append(trend_confidence)
            
            # Фактор объема (подтверждение движений)
            volume_confirmation = volume_metrics['trend_confirmation']
            confidence_factors.append(volume_confirmation)
            
            # Общая уверенность
            overall_confidence = np.mean(confidence_factors)
            
            return float(max(0.1, min(1.0, overall_confidence)))
            
        except Exception as e:
            logger.error(f"Ошибка расчета уверенности: {e}")
            return 0.5
    
    @staticmethod
    def _analyze_regime_stability(df: pd.DataFrame, current_regime: MarketRegime, 
                                period: int) -> Dict[str, Union[int, float]]:
        """Анализ стабильности текущего режима"""
        try:
            # Простой анализ - оценка стабильности через волатильность волатильности
            returns = df['close'].pct_change().dropna()
            vol_rolling = returns.rolling(10).std()
            vol_stability = 1 - vol_rolling.tail(period).std()
            
            # Примерная длительность режима (упрощенная оценка)
            # В реальности нужно было бы хранить историю режимов
            duration = min(period, 20)  # Заглушка
            
            return {
                'duration': duration,
                'stability': float(max(0, min(1, vol_stability)))
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа стабильности режима: {e}")
            return {'duration': 10, 'stability': 0.5}
    
    @staticmethod
    def _get_default_condition() -> MarketCondition:
        """Получение базового состояния рынка при ошибках"""
        return MarketCondition(
            regime=MarketRegime.NORMAL,
            volatility=0.02,
            trend_strength=0.3,
            trend_direction=0,
            volume_activity=1.0,
            momentum=0.0,
            confidence=0.5,
            atr_normalized=0.01,
            range_efficiency=0.5,
            consolidation_factor=0.5,
            breakout_potential=0.3,
            regime_duration=10,
            stability=0.5
        )


class MultiTimeframeAnalyzer:
    """Анализатор рыночных условий для нескольких таймфреймов"""
    
    @staticmethod
    def analyze_multiple_timeframes(data: Dict[str, pd.DataFrame],
                                  timeframes: List[TimeFrame]) -> Dict[str, MarketCondition]:
        """
        Анализ рыночных условий на нескольких таймфреймах
        
        Args:
            data: Словарь {timeframe: DataFrame}
            timeframes: Список таймфреймов для анализа
        
        Returns:
            Словарь с условиями для каждого таймфрейма
        """
        conditions = {}
        
        for tf in timeframes:
            tf_key = tf.value
            if tf_key in data:
                # Адаптируем период анализа под таймфрейм
                period = MultiTimeframeAnalyzer._get_adaptive_period(tf)
                short_period = max(period // 3, 10)
                
                condition = MarketRegimeAnalyzer.analyze_market_condition(
                    data[tf_key], period, short_period
                )
                conditions[tf_key] = condition
            else:
                logger.warning(f"Отсутствуют данные для таймфрейма {tf_key}")
        
        return conditions
    
    @staticmethod
    def _get_adaptive_period(timeframe: TimeFrame) -> int:
        """Получение адаптивного периода анализа для таймфрейма"""
        # Базовые периоды для разных ТФ
        base_periods = {
            TimeFrame.M1: 120,   # 2 часа
            TimeFrame.M5: 60,    # 5 часов
            TimeFrame.M15: 40,   # 10 часов
            TimeFrame.M30: 30,   # 15 часов
            TimeFrame.H1: 24,    # 1 день
            TimeFrame.H4: 18,    # 3 дня
            TimeFrame.D1: 14,    # 2 недели
            TimeFrame.W1: 12     # 3 месяца
        }
        
        return base_periods.get(timeframe, 50)
    
    @staticmethod
    def get_consensus_condition(conditions: Dict[str, MarketCondition],
                              timeframe_weights: Optional[Dict[str, float]] = None) -> MarketCondition:
        """
        Получение консенсусного состояния рынка из нескольких таймфреймов
        
        Args:
            conditions: Условия для разных таймфреймов
            timeframe_weights: Веса для каждого таймфрейма (опционально)
        
        Returns:
            Консенсусное состояние рынка
        """
        if not conditions:
            return MarketRegimeAnalyzer._get_default_condition()
        
        if timeframe_weights is None:
            # Равные веса по умолчанию
            timeframe_weights = {tf: 1.0 for tf in conditions.keys()}
        
        # Нормализуем веса
        total_weight = sum(timeframe_weights.values())
        normalized_weights = {tf: w / total_weight for tf, w in timeframe_weights.items()}
        
        # Взвешенные средние для числовых параметров
        weighted_volatility = sum(
            conditions[tf].volatility * normalized_weights.get(tf, 0)
            for tf in conditions.keys()
        )
        
        weighted_trend_strength = sum(
            conditions[tf].trend_strength * normalized_weights.get(tf, 0)
            for tf in conditions.keys()
        )
        
        weighted_momentum = sum(
            conditions[tf].momentum * normalized_weights.get(tf, 0)
            for tf in conditions.keys()
        )
        
        # Определение консенсусного режима (голосование)
        regime_votes = {}
        for tf, condition in conditions.items():
            weight = normalized_weights.get(tf, 0)
            regime = condition.regime
            regime_votes[regime] = regime_votes.get(regime, 0) + weight
        
        consensus_regime = max(regime_votes.keys(), key=lambda k: regime_votes[k])
        
        # Консенсусное направление тренда
        direction_votes = sum(
            conditions[tf].trend_direction * normalized_weights.get(tf, 0)
            for tf in conditions.keys()
        )
        consensus_direction = 1 if direction_votes > 0.1 else -1 if direction_votes < -0.1 else 0
        
        # Средняя уверенность
        avg_confidence = np.mean([c.confidence for c in conditions.values()])
        
        return MarketCondition(
            regime=consensus_regime,
            volatility=weighted_volatility,
            trend_strength=weighted_trend_strength,
            trend_direction=consensus_direction,
            volume_activity=np.mean([c.volume_activity for c in conditions.values()]),
            momentum=weighted_momentum,
            confidence=avg_confidence,
            atr_normalized=np.mean([c.atr_normalized for c in conditions.values()]),
            range_efficiency=np.mean([c.range_efficiency for c in conditions.values()]),
            consolidation_factor=np.mean([c.consolidation_factor for c in conditions.values()]),
            breakout_potential=np.mean([c.breakout_potential for c in conditions.values()]),
            regime_duration=int(np.mean([c.regime_duration for c in conditions.values()])),
            stability=np.mean([c.stability for c in conditions.values()])
        )


# =========================================================================
# УТИЛИТНЫЕ ФУНКЦИИ
# =========================================================================

def quick_market_check(df: pd.DataFrame) -> str:
    """
    Быстрая оценка состояния рынка (одной строкой)
    
    Returns:
        Строка с кратким описанием состояния рынка
    """
    try:
        condition = MarketRegimeAnalyzer.analyze_market_condition(df, period=30, short_period=10)
        
        trend_desc = "📈 Растет" if condition.is_bullish else "📉 Падает" if condition.is_bearish else "➡️ Боковик"
        vol_desc = "🔥 Волатильно" if condition.is_volatile else "😴 Спокойно"
        
        return f"{condition.regime.value.title()} | {trend_desc} | {vol_desc} | Сила: {condition.trend_strength:.1f}"
        
    except Exception as e:
        logger.error(f"Ошибка быстрой проверки рынка: {e}")
        return "❓ Неопределенно"


def get_trading_session_analysis(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Анализ торговой сессии
    
    Returns:
        Словарь с анализом текущей сессии
    """
    try:
        condition = MarketRegimeAnalyzer.analyze_market_condition(df)
        
        # Рекомендации для торговли
        recommendations = []
        
        if condition.is_trending and condition.trend_strength > 0.7:
            recommendations.append("✅ Хорошие условия для трендовых стратегий")
        
        if condition.is_volatile:
            recommendations.append("⚠️ Высокая волатильность - осторожность с размером позиций")
        
        if condition.consolidation_factor > 0.7:
            recommendations.append("📊 Рынок в консолидации - ожидайте пробоя")
        
        if condition.volume_activity > 1.5:
            recommendations.append("📈 Высокая активность - подтверждение движений")
        
        if not recommendations:
            recommendations.append("🔍 Нейтральные условия - стандартные параметры")
        
        return {
            'condition': condition,
            'summary': str(condition),
            'recommendations': recommendations,
            'risk_level': 'High' if condition.is_volatile else 'Medium' if condition.is_trending else 'Low',
            'best_strategies': _get_optimal_strategies(condition)
        }
        
    except Exception as e:
        logger.error(f"Ошибка анализа торговой сессии: {e}")
        return {
            'summary': "Ошибка анализа",
            'recommendations': ["❌ Не удалось проанализировать условия"],
            'risk_level': 'Unknown'
        }


def _get_optimal_strategies(condition: MarketCondition) -> List[str]:
    """Получение оптимальных стратегий для текущих условий"""
    strategies = []
    
    if condition.is_trending and condition.trend_strength > 0.6:
        strategies.append("Trend Following")
        strategies.append("Momentum")
    
    if condition.consolidation_factor > 0.6:
        strategies.append("Range Trading")
        strategies.append("Mean Reversion")
    
    if condition.is_volatile:
        strategies.append("Volatility Breakout")
        strategies.append("News Trading")
    
    if condition.volume_activity > 1.3:
        strategies.append("Volume Analysis")
        strategies.append("Order Flow")
    
    if not strategies:
        strategies.append("Scalping")
        strategies.append("Conservative")
    
    return strategies


# =========================================================================
# КОНСТАНТЫ И НАСТРОЙКИ
# =========================================================================

# Пороги для классификации рыночных режимов
REGIME_THRESHOLDS = {
    'volatility': {
        'low': 0.01,
        'normal': 0.02,
        'high': 0.03,
        'extreme': 0.05
    },
    'trend_strength': {
        'weak': 0.3,
        'moderate': 0.5,
        'strong': 0.7,
        'very_strong': 0.85
    },
    'volume_activity': {
        'low': 0.5,
        'normal': 1.0,
        'high': 1.5,
        'extreme': 2.5
    }
}

# Рекомендуемые параметры для разных режимов
REGIME_ADAPTATIONS = {
    MarketRegime.VOLATILE: {
        'stop_loss_multiplier': 1.2,
        'position_size_multiplier': 0.7,
        'signal_threshold_multiplier': 1.3
    },
    MarketRegime.TRENDING: {
        'stop_loss_multiplier': 0.8,
        'position_size_multiplier': 1.2,
        'risk_reward_multiplier': 1.3
    },
    MarketRegime.SIDEWAYS: {
        'stop_loss_multiplier': 1.1,
        'signal_threshold_multiplier': 1.2,
        'confluence_required_bonus': 1
    },
    MarketRegime.NORMAL: {
        'stop_loss_multiplier': 1.0,
        'position_size_multiplier': 1.0,
        'signal_threshold_multiplier': 1.0
    }
}