# bot/strategy/utils/validators.py
"""
Централизованная система валидации данных для торговых стратегий
Обеспечивает качество и консистентность входных данных
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any
from datetime import datetime, timezone, timedelta
import logging
from dataclasses import dataclass
from enum import Enum

from ..base.enums import ValidationLevel, TimeFrame

# Настройка логирования
logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Исключение для ошибок валидации"""
    pass


class DataQuality(Enum):
    """Уровни качества данных"""
    EXCELLENT = "excellent"
    GOOD = "good"  
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Результат валидации данных"""
    is_valid: bool
    quality: DataQuality
    errors: List[str]
    warnings: List[str]
    data_points: int
    missing_data_pct: float
    time_coverage: Optional[timedelta]
    recommendations: List[str]
    
    @property
    def has_errors(self) -> bool:
        """Проверка наличия ошибок"""
        return len(self.errors) > 0
    
    @property  
    def has_warnings(self) -> bool:
        """Проверка наличия предупреждений"""
        return len(self.warnings) > 0
    
    @property
    def is_usable(self) -> bool:
        """Проверка пригодности данных для использования"""
        return self.is_valid and self.quality != DataQuality.CRITICAL
    
    def __str__(self) -> str:
        status = "✅ ВАЛИДНЫ" if self.is_valid else "❌ НЕ ВАЛИДНЫ"
        return f"Данные {status} | Качество: {self.quality.value} | Точек: {self.data_points}"


class DataValidator:
    """
    Централизованный класс для валидации торговых данных
    Поддерживает различные уровни строгости валидации
    """
    
    # Требуемые колонки для разных типов данных
    OHLC_COLUMNS = ['open', 'high', 'low', 'close']
    OHLCV_COLUMNS = OHLC_COLUMNS + ['volume']
    DELTA_COLUMNS = OHLCV_COLUMNS + ['delta']
    EXTENDED_COLUMNS = OHLCV_COLUMNS + ['buy_volume', 'sell_volume']
    
    @staticmethod
    def validate_basic_data(df: pd.DataFrame, 
                          validation_level: ValidationLevel = ValidationLevel.STANDARD,
                          required_columns: Optional[List[str]] = None) -> ValidationResult:
        """
        Базовая валидация OHLCV данных
        
        Args:
            df: DataFrame для валидации
            validation_level: Уровень строгости валидации
            required_columns: Список требуемых колонок (по умолчанию OHLCV)
        
        Returns:
            ValidationResult с результатами валидации
        """
        errors = []
        warnings = []
        recommendations = []
        
        # Используем OHLCV колонки по умолчанию
        if required_columns is None:
            required_columns = DataValidator.OHLCV_COLUMNS
        
        try:
            # 1. Проверка на пустой DataFrame
            if df is None:
                errors.append("DataFrame равен None")
                return ValidationResult(
                    is_valid=False, quality=DataQuality.CRITICAL, 
                    errors=errors, warnings=warnings, data_points=0,
                    missing_data_pct=100.0, time_coverage=None,
                    recommendations=["Предоставьте корректные данные"]
                )
            
            if df.empty:
                errors.append("DataFrame пуст")
                return ValidationResult(
                    is_valid=False, quality=DataQuality.CRITICAL,
                    errors=errors, warnings=warnings, data_points=0,
                    missing_data_pct=100.0, time_coverage=None,
                    recommendations=["Загрузите данные перед валидацией"]
                )
            
            data_points = len(df)
            
            # 2. Проверка минимального количества данных
            min_required = validation_level.min_data_points
            if data_points < min_required:
                errors.append(f"Недостаточно данных: {data_points} < {min_required}")
            
            # 3. Проверка наличия требуемых колонок
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                errors.append(f"Отсутствуют колонки: {missing_columns}")
                return ValidationResult(
                    is_valid=False, quality=DataQuality.CRITICAL,
                    errors=errors, warnings=warnings, data_points=data_points,
                    missing_data_pct=100.0, time_coverage=None,
                    recommendations=[f"Добавьте колонки: {missing_columns}"]
                )
            
            # 4. Конвертация в числовые значения и проверка типов
            numeric_errors = []
            for col in required_columns:
                if col in df.columns:
                    try:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    except Exception as e:
                        numeric_errors.append(f"Ошибка конвертации {col}: {e}")
            
            if numeric_errors:
                errors.extend(numeric_errors)
            
            # 5. Проверка на NaN значения
            nan_check = df[required_columns].isnull()
            total_nan = nan_check.sum().sum()
            total_values = len(df) * len(required_columns)
            missing_data_pct = (total_nan / total_values) * 100
            
            if validation_level == ValidationLevel.PARANOID and total_nan > 0:
                errors.append(f"Обнаружены NaN значения: {total_nan}")
            elif validation_level == ValidationLevel.STRICT and missing_data_pct > 1:
                errors.append(f"Слишком много NaN значений: {missing_data_pct:.1f}%")
            elif missing_data_pct > 5:
                warnings.append(f"Много пропущенных данных: {missing_data_pct:.1f}%")
            
            # 6. Проверка логичности OHLC данных
            if all(col in df.columns for col in DataValidator.OHLC_COLUMNS):
                ohlc_issues = DataValidator._validate_ohlc_logic(df)
                if ohlc_issues:
                    if validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID]:
                        errors.extend(ohlc_issues)
                    else:
                        warnings.extend(ohlc_issues)
            
            # 7. Проверка на нулевые и отрицательные цены
            price_columns = [col for col in DataValidator.OHLC_COLUMNS if col in df.columns]
            invalid_prices = (df[price_columns] <= 0).any().any()
            if invalid_prices:
                errors.append("Обнаружены нулевые или отрицательные цены")
            
            # 8. Проверка объемов (если есть)
            if 'volume' in df.columns:
                negative_volume = (df['volume'] < 0).any()
                if negative_volume:
                    errors.append("Обнаружены отрицательные объемы")
                
                zero_volume_pct = (df['volume'] == 0).sum() / len(df) * 100
                if zero_volume_pct > 10:
                    warnings.append(f"Много нулевых объемов: {zero_volume_pct:.1f}%")
            
            # 9. Проверка временных меток (если индекс является datetime)
            time_coverage = None
            if isinstance(df.index, pd.DatetimeIndex):
                time_issues = DataValidator._validate_time_series(df, validation_level)
                warnings.extend(time_issues)
                
                if len(df) > 1:
                    time_coverage = df.index[-1] - df.index[0]
            
            # 10. Проверка на выбросы (для строгих уровней)
            if validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID]:
                outlier_issues = DataValidator._detect_outliers(df, required_columns)
                if outlier_issues:
                    warnings.extend(outlier_issues)
            
            # 11. Определение качества данных
            quality = DataValidator._determine_data_quality(
                len(errors), len(warnings), missing_data_pct, data_points, min_required
            )
            
            # 12. Генерация рекомендаций
            recommendations = DataValidator._generate_recommendations(
                quality, missing_data_pct, data_points, min_required, validation_level
            )
            
            # Итоговый результат
            is_valid = len(errors) == 0 and quality != DataQuality.CRITICAL
            
            return ValidationResult(
                is_valid=is_valid,
                quality=quality,
                errors=errors,
                warnings=warnings,
                data_points=data_points,
                missing_data_pct=missing_data_pct,
                time_coverage=time_coverage,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Критическая ошибка валидации: {e}")
            return ValidationResult(
                is_valid=False,
                quality=DataQuality.CRITICAL,
                errors=[f"Критическая ошибка валидации: {str(e)}"],
                warnings=[],
                data_points=len(df) if df is not None else 0,
                missing_data_pct=100.0,
                time_coverage=None,
                recommendations=["Проверьте формат и структуру данных"]
            )
    
    @staticmethod
    def _validate_ohlc_logic(df: pd.DataFrame) -> List[str]:
        """Проверка логичности OHLC данных"""
        issues = []
        
        try:
            # Проверка что high >= low
            high_low_invalid = (df['low'] > df['high']).any()
            if high_low_invalid:
                issues.append("Обнаружены бары где low > high")
            
            # Проверка что open и close в диапазоне high-low  
            open_invalid = ((df['open'] > df['high']) | (df['open'] < df['low'])).any()
            if open_invalid:
                issues.append("Обнаружены бары где open вне диапазона high-low")
            
            close_invalid = ((df['close'] > df['high']) | (df['close'] < df['low'])).any()
            if close_invalid:
                issues.append("Обнаружены бары где close вне диапазона high-low")
            
            # Проверка на подозрительно большие диапазоны
            ranges = (df['high'] - df['low']) / df['close']
            large_ranges = (ranges > 0.1).sum()  # Диапазон больше 10%
            if large_ranges > len(df) * 0.05:  # Больше 5% от всех баров
                issues.append(f"Много баров с большими диапазонами: {large_ranges}")
                
        except Exception as e:
            issues.append(f"Ошибка проверки OHLC логики: {e}")
        
        return issues
    
    @staticmethod
    def _validate_time_series(df: pd.DataFrame, validation_level: ValidationLevel) -> List[str]:
        """Валидация временных рядов"""
        issues = []
        
        try:
            if not isinstance(df.index, pd.DatetimeIndex):
                return ["Индекс не является DatetimeIndex"]
            
            # Проверка на дубликаты временных меток
            duplicates = df.index.duplicated().sum()
            if duplicates > 0:
                issues.append(f"Обнаружены дублирующиеся временные метки: {duplicates}")
            
            # Проверка сортировки по времени
            if not df.index.is_monotonic_increasing:
                issues.append("Данные не отсортированы по времени")
            
            # Проверка пропусков во времени (для строгих уровней)
            if validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID] and len(df) > 2:
                time_diffs = df.index.to_series().diff().dropna()
                median_diff = time_diffs.median()
                
                # Находим значительные пропуски (больше чем 2x медианный интервал)
                large_gaps = (time_diffs > median_diff * 2).sum()
                if large_gaps > 0:
                    issues.append(f"Обнаружены пропуски во времени: {large_gaps}")
            
            # Проверка актуальности данных
            if len(df) > 0:
                last_time = df.index[-1]
                if pd.Timestamp.now(tz=timezone.utc) - last_time > timedelta(hours=24):
                    issues.append("Данные могут быть устаревшими (старше 24 часов)")
                    
        except Exception as e:
            issues.append(f"Ошибка валидации временных рядов: {e}")
        
        return issues
    
    @staticmethod
    def _detect_outliers(df: pd.DataFrame, columns: List[str]) -> List[str]:
        """Детекция выбросов в данных"""
        issues = []
        
        try:
            for col in columns:
                if col not in df.columns:
                    continue
                
                # Используем IQR метод для детекции выбросов
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                outliers = ((df[col] < lower_bound) | (df[col] > upper_bound)).sum()
                outlier_pct = outliers / len(df) * 100
                
                if outlier_pct > 5:  # Больше 5% выбросов
                    issues.append(f"Много выбросов в колонке {col}: {outlier_pct:.1f}%")
                    
        except Exception as e:
            issues.append(f"Ошибка детекции выбросов: {e}")
        
        return issues
    
    @staticmethod
    def _determine_data_quality(errors_count: int, warnings_count: int, 
                              missing_pct: float, data_points: int, min_required: int) -> DataQuality:
        """Определение качества данных"""
        
        if errors_count > 0:
            return DataQuality.CRITICAL
        
        # Оценка на основе различных факторов
        quality_score = 100
        
        # Штрафы за предупреждения
        quality_score -= warnings_count * 5
        
        # Штрафы за пропущенные данные
        if missing_pct > 10:
            quality_score -= 30
        elif missing_pct > 5:
            quality_score -= 15
        elif missing_pct > 1:
            quality_score -= 5
        
        # Штрафы за недостаток данных
        data_ratio = data_points / min_required
        if data_ratio < 1.5:
            quality_score -= 20
        elif data_ratio < 2:
            quality_score -= 10
        
        # Определение качества по итоговому счету
        if quality_score >= 90:
            return DataQuality.EXCELLENT
        elif quality_score >= 75:
            return DataQuality.GOOD
        elif quality_score >= 60:
            return DataQuality.ACCEPTABLE
        elif quality_score >= 40:
            return DataQuality.POOR
        else:
            return DataQuality.CRITICAL
    
    @staticmethod
    def _generate_recommendations(quality: DataQuality, missing_pct: float, 
                                data_points: int, min_required: int,
                                validation_level: ValidationLevel) -> List[str]:
        """Генерация рекомендаций по улучшению данных"""
        recommendations = []
        
        if quality == DataQuality.CRITICAL:
            recommendations.append("🚨 Критические проблемы с данными - использование невозможно")
            recommendations.append("Проверьте источник данных и формат файла")
        
        if data_points < min_required:
            needed = min_required - data_points
            recommendations.append(f"📊 Загрузите еще {needed} точек данных")
        
        if missing_pct > 10:
            recommendations.append("🔍 Проверьте источник данных - слишком много пропусков")
        elif missing_pct > 5:
            recommendations.append("⚠️ Рассмотрите заполнение пропущенных значений")
        
        if quality == DataQuality.POOR:
            recommendations.append("📈 Увеличьте качество данных перед использованием")
            recommendations.append("Проверьте настройки источника данных")
        
        if validation_level == ValidationLevel.BASIC and quality in [DataQuality.GOOD, DataQuality.EXCELLENT]:
            recommendations.append("✨ Данные хорошего качества - можно использовать")
        
        if not recommendations:
            recommendations.append("✅ Данные готовы к использованию")
        
        return recommendations


class MultiTimeframeValidator:
    """Специализированный валидатор для мультитаймфрейм данных"""
    
    @staticmethod
    def validate_multitimeframe_data(data: Dict[str, pd.DataFrame], 
                                   required_timeframes: List[TimeFrame],
                                   validation_level: ValidationLevel = ValidationLevel.STANDARD) -> Dict[str, ValidationResult]:
        """
        Валидация данных для нескольких таймфреймов
        
        Args:
            data: Словарь {timeframe: DataFrame}
            required_timeframes: Список требуемых таймфреймов
            validation_level: Уровень валидации
        
        Returns:
            Словарь с результатами валидации для каждого ТФ
        """
        results = {}
        
        # Валидация каждого таймфрейма отдельно
        for tf in required_timeframes:
            tf_key = tf.value
            
            if tf_key not in data:
                results[tf_key] = ValidationResult(
                    is_valid=False,
                    quality=DataQuality.CRITICAL,
                    errors=[f"Отсутствуют данные для таймфрейма {tf_key}"],
                    warnings=[],
                    data_points=0,
                    missing_data_pct=100.0,
                    time_coverage=None,
                    recommendations=[f"Загрузите данные для {tf_key}"]
                )
                continue
            
            # Базовая валидация для каждого ТФ
            result = DataValidator.validate_basic_data(data[tf_key], validation_level)
            results[tf_key] = result
        
        # Дополнительная проверка синхронизации между ТФ
        sync_issues = MultiTimeframeValidator._check_timeframe_synchronization(data, required_timeframes)
        
        # Добавляем проблемы синхронизации к результатам
        if sync_issues:
            for tf_key in results:
                if results[tf_key].is_valid:
                    results[tf_key].warnings.extend(sync_issues)
        
        return results
    
    @staticmethod
    def _check_timeframe_synchronization(data: Dict[str, pd.DataFrame], 
                                       timeframes: List[TimeFrame]) -> List[str]:
        """Проверка синхронизации между таймфреймами"""
        issues = []
        
        try:
            available_data = {tf.value: data[tf.value] for tf in timeframes if tf.value in data}
            
            if len(available_data) < 2:
                return issues  # Нужно минимум 2 ТФ для проверки синхронизации
            
            # Проверяем последние временные метки
            last_times = {}
            for tf_key, df in available_data.items():
                if isinstance(df.index, pd.DatetimeIndex) and len(df) > 0:
                    last_times[tf_key] = df.index[-1]
            
            if len(last_times) >= 2:
                times = list(last_times.values())
                max_time = max(times)
                min_time = min(times)
                time_diff = (max_time - min_time).total_seconds()
                
                # Допустимое расхождение зависит от таймфреймов
                max_allowed_diff = max([tf.seconds for tf in timeframes]) * 2
                
                if time_diff > max_allowed_diff:
                    issues.append(f"Большое расхождение времени между ТФ: {time_diff}s")
            
            # Проверяем покрытие данных
            data_coverage = {}
            for tf_key, df in available_data.items():
                if isinstance(df.index, pd.DatetimeIndex) and len(df) > 1:
                    coverage = df.index[-1] - df.index[0]
                    data_coverage[tf_key] = coverage
            
            if data_coverage:
                coverages = list(data_coverage.values())
                min_coverage = min(coverages)
                max_coverage = max(coverages)
                
                # Если разница в покрытии слишком большая
                if max_coverage > min_coverage * 2:
                    issues.append("Значительная разница в покрытии данных между ТФ")
                    
        except Exception as e:
            issues.append(f"Ошибка проверки синхронизации ТФ: {e}")
        
        return issues


class StrategyDataValidator:
    """Валидатор данных для конкретных типов стратегий"""
    
    @staticmethod
    def validate_volume_vwap_data(df: pd.DataFrame, 
                                 validation_level: ValidationLevel = ValidationLevel.STANDARD) -> ValidationResult:
        """Валидация данных для VWAP стратегии"""
        # Проверяем наличие объемных данных
        required_columns = DataValidator.OHLCV_COLUMNS
        result = DataValidator.validate_basic_data(df, validation_level, required_columns)
        
        # Дополнительные проверки для VWAP
        if result.is_valid and 'volume' in df.columns:
            # Проверка качества объемных данных
            zero_volume_count = (df['volume'] == 0).sum()
            if zero_volume_count > len(df) * 0.1:  # Больше 10% нулевых объемов
                result.warnings.append(f"Много нулевых объемов: {zero_volume_count}")
                result.recommendations.append("Проверьте источник объемных данных")
        
        return result
    
    @staticmethod
    def validate_cumdelta_data(df: pd.DataFrame,
                              validation_level: ValidationLevel = ValidationLevel.STANDARD) -> ValidationResult:
        """Валидация данных для CumDelta стратегии"""
        # Проверяем наличие данных о дельте
        has_delta_columns = any(col in df.columns for col in ['delta', 'buy_volume', 'sell_volume'])
        
        if has_delta_columns:
            # Если есть специализированные колонки
            available_cols = [col for col in ['delta', 'buy_volume', 'sell_volume'] if col in df.columns]
            required_columns = DataValidator.OHLCV_COLUMNS + available_cols
        else:
            # Если только базовые OHLCV
            required_columns = DataValidator.OHLCV_COLUMNS
        
        result = DataValidator.validate_basic_data(df, validation_level, required_columns)
        
        # Дополнительные проверки для дельты
        if result.is_valid:
            if not has_delta_columns:
                result.warnings.append("Нет данных о дельте - будет использован fallback расчет")
                result.recommendations.append("Добавьте колонки delta или buy_volume/sell_volume для лучшей точности")
        
        return result
    
    @staticmethod
    def validate_multitf_data(data: Dict[str, pd.DataFrame], 
                             fast_tf: TimeFrame, slow_tf: TimeFrame,
                             validation_level: ValidationLevel = ValidationLevel.STANDARD) -> Dict[str, ValidationResult]:
        """Валидация данных для Multi-timeframe стратегии"""
        return MultiTimeframeValidator.validate_multitimeframe_data(
            data, [fast_tf, slow_tf], validation_level
        )


# =========================================================================
# УТИЛИТНЫЕ ФУНКЦИИ
# =========================================================================

def quick_validate(df: pd.DataFrame, strategy_type: str = "basic") -> bool:
    """
    Быстрая валидация данных (только критические проверки)
    
    Args:
        df: DataFrame для проверки
        strategy_type: Тип стратегии ("basic", "volume_vwap", "cumdelta", "multitf")
    
    Returns:
        bool: True если данные пригодны к использованию
    """
    try:
        if strategy_type == "volume_vwap":
            result = StrategyDataValidator.validate_volume_vwap_data(df, ValidationLevel.BASIC)
        elif strategy_type == "cumdelta":
            result = StrategyDataValidator.validate_cumdelta_data(df, ValidationLevel.BASIC)
        else:
            result = DataValidator.validate_basic_data(df, ValidationLevel.BASIC)
        
        return result.is_usable
        
    except Exception as e:
        logger.error(f"Ошибка быстрой валидации: {e}")
        return False


def validate_and_log(df: pd.DataFrame, strategy_name: str = "Unknown",
                    validation_level: ValidationLevel = ValidationLevel.STANDARD) -> ValidationResult:
    """
    Валидация с автоматическим логированием результатов
    """
    result = DataValidator.validate_basic_data(df, validation_level)
    
    # Логирование результатов
    log_level = logging.INFO if result.is_valid else logging.WARNING
    logger.log(log_level, f"[{strategy_name}] {result}")
    
    if result.has_errors:
        for error in result.errors:
            logger.error(f"[{strategy_name}] ❌ {error}")
    
    if result.has_warnings:
        for warning in result.warnings:
            logger.warning(f"[{strategy_name}] ⚠️ {warning}")
    
    if result.recommendations:
        for rec in result.recommendations:
            logger.info(f"[{strategy_name}] 💡 {rec}")
    
    return result


def get_validation_summary(results: Dict[str, ValidationResult]) -> Dict[str, Any]:
    """
    Создание сводки по результатам валидации
    
    Args:
        results: Словарь с результатами валидации
    
    Returns:
        Словарь со сводной информацией
    """
    total_datasets = len(results)
    valid_datasets = sum(1 for r in results.values() if r.is_valid)
    usable_datasets = sum(1 for r in results.values() if r.is_usable)
    
    quality_distribution = {}
    for quality in DataQuality:
        count = sum(1 for r in results.values() if r.quality == quality)
        quality_distribution[quality.value] = count
    
    total_errors = sum(len(r.errors) for r in results.values())
    total_warnings = sum(len(r.warnings) for r in results.values())
    
    return {
        "total_datasets": total_datasets,
        "valid_datasets": valid_datasets,
        "usable_datasets": usable_datasets,
        "validation_rate": valid_datasets / total_datasets if total_datasets > 0 else 0,
        "usability_rate": usable_datasets / total_datasets if total_datasets > 0 else 0,
        "quality_distribution": quality_distribution,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "overall_quality": "good" if usable_datasets / total_datasets > 0.8 else "poor" if total_datasets > 0 else "unknown"
    }


# =========================================================================
# КОНСТАНТЫ И НАСТРОЙКИ
# =========================================================================

# Минимальные требования для разных типов стратегий
STRATEGY_MIN_DATA_REQUIREMENTS = {
    "volume_vwap": 100,
    "cumdelta": 80,
    "multitf": 150,
    "scalping": 50,
    "swing": 200
}

# Критические пороги для разных метрик
CRITICAL_THRESHOLDS = {
    "missing_data_pct": 20.0,  # Максимальный процент пропущенных данных
    "outlier_pct": 10.0,       # Максимальный процент выбросов
    "zero_volume_pct": 15.0,   # Максимальный процент нулевых объемов
    "time_gap_hours": 4.0      # Максимальный пропуск во времени (часы)
}

# Рекомендуемые настройки валидации для разных сред
VALIDATION_PRESETS = {
    "development": ValidationLevel.BASIC,
    "testing": ValidationLevel.STANDARD,  
    "staging": ValidationLevel.STRICT,
    "production": ValidationLevel.PARANOID
}