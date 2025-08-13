# bot/strategy/utils/levels.py
"""
Система поиска уровней поддержки и сопротивления для торговых стратегий
Включает различные алгоритмы определения ключевых уровней
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime, timedelta

# Настройка логирования
logger = logging.getLogger(__name__)


class LevelType(Enum):
    """Типы уровней"""
    SUPPORT = "support"
    RESISTANCE = "resistance"
    PIVOT = "pivot"
    BREAKOUT = "breakout"


class LevelStrength(Enum):
    """Сила уровня"""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    CRITICAL = "critical"


@dataclass
class PriceLevel:
    """Класс для представления ценового уровня"""
    price: float
    level_type: LevelType
    strength: LevelStrength
    touches: int  # Количество касаний уровня
    first_touch: datetime
    last_touch: datetime
    confidence: float  # Уверенность в уровне (0-1)
    volume_at_level: float  # Средний объем на уровне
    age_days: float  # Возраст уровня в днях
    
    @property
    def is_fresh(self) -> bool:
        """Проверка свежести уровня (меньше 30 дней)"""
        return self.age_days < 30
    
    @property
    def is_reliable(self) -> bool:
        """Проверка надежности уровня"""
        return self.touches >= 2 and self.confidence > 0.6
    
    @property
    def is_strong(self) -> bool:
        """Проверка силы уровня"""
        return self.strength in [LevelStrength.STRONG, LevelStrength.CRITICAL]
    
    def distance_to_price(self, current_price: float) -> float:
        """Расчет расстояния до текущей цены в процентах"""
        return abs(self.price - current_price) / current_price * 100
    
    def __str__(self) -> str:
        return f"{self.level_type.value.title()} {self.price:.2f} ({self.strength.value}, {self.touches} touches)"


class LevelsFinder:
    """
    Основной класс для поиска уровней поддержки и сопротивления
    Содержит различные алгоритмы и методы анализа
    """
    
    @staticmethod
    def find_swing_levels(df: pd.DataFrame, 
                         lookback: int = 20,
                         min_touches: int = 2,
                         tolerance_pct: float = 0.1) -> List[PriceLevel]:
        """
        Поиск уровней на основе swing high/low точек
        
        Args:
            df: DataFrame с OHLC данными
            lookback: Период поиска назад
            min_touches: Минимальное количество касаний
            tolerance_pct: Толерантность для группировки уровней (%)
        
        Returns:
            Список найденных уровней
        """
        try:
            if len(df) < lookback * 2:
                logger.warning(f"Недостаточно данных для поиска swing уровней: {len(df)}")
                return []
            
            levels = []
            
            # Поиск swing highs (сопротивления)
            swing_highs = LevelsFinder._find_swing_highs(df, lookback)
            resistance_levels = LevelsFinder._group_levels(
                swing_highs, tolerance_pct, LevelType.RESISTANCE, df
            )
            levels.extend(resistance_levels)
            
            # Поиск swing lows (поддержки)
            swing_lows = LevelsFinder._find_swing_lows(df, lookback)
            support_levels = LevelsFinder._group_levels(
                swing_lows, tolerance_pct, LevelType.SUPPORT, df
            )
            levels.extend(support_levels)
            
            # Фильтрация по минимальному количеству касаний
            filtered_levels = [level for level in levels if level.touches >= min_touches]
            
            # Сортировка по силе уровня
            filtered_levels.sort(key=lambda x: (x.strength.value, x.confidence), reverse=True)
            
            return filtered_levels
            
        except Exception as e:
            logger.error(f"Ошибка поиска swing уровней: {e}")
            return []
    
    @staticmethod
    def _find_swing_highs(df: pd.DataFrame, lookback: int) -> List[Tuple[int, float, datetime]]:
        """Поиск swing high точек"""
        swing_highs = []
        
        for i in range(lookback, len(df) - lookback):
            current_high = df['high'].iloc[i]
            
            # Проверяем, является ли текущая точка локальным максимумом
            left_side = df['high'].iloc[i-lookback:i]
            right_side = df['high'].iloc[i+1:i+lookback+1]
            
            if (current_high >= left_side.max() and 
                current_high >= right_side.max()):
                
                timestamp = df.index[i] if hasattr(df.index[i], 'to_pydatetime') else datetime.now()
                swing_highs.append((i, current_high, timestamp))
        
        return swing_highs
    
    @staticmethod
    def _find_swing_lows(df: pd.DataFrame, lookback: int) -> List[Tuple[int, float, datetime]]:
        """Поиск swing low точек"""
        swing_lows = []
        
        for i in range(lookback, len(df) - lookback):
            current_low = df['low'].iloc[i]
            
            # Проверяем, является ли текущая точка локальным минимумом
            left_side = df['low'].iloc[i-lookback:i]
            right_side = df['low'].iloc[i+1:i+lookback+1]
            
            if (current_low <= left_side.min() and 
                current_low <= right_side.min()):
                
                timestamp = df.index[i] if hasattr(df.index[i], 'to_pydatetime') else datetime.now()
                swing_lows.append((i, current_low, timestamp))
        
        return swing_lows
    
    @staticmethod
    def _group_levels(swing_points: List[Tuple[int, float, datetime]], 
                     tolerance_pct: float, 
                     level_type: LevelType,
                     df: pd.DataFrame) -> List[PriceLevel]:
        """Группировка близких уровней в один"""
        if not swing_points:
            return []
        
        # Сортируем по цене
        swing_points.sort(key=lambda x: x[1])
        
        grouped_levels = []
        current_group = [swing_points[0]]
        
        for i in range(1, len(swing_points)):
            current_price = swing_points[i][1]
            group_avg_price = sum(point[1] for point in current_group) / len(current_group)
            
            # Проверяем, попадает ли точка в текущую группу
            if abs(current_price - group_avg_price) / group_avg_price * 100 <= tolerance_pct:
                current_group.append(swing_points[i])
            else:
                # Создаем уровень из текущей группы
                if len(current_group) >= 1:
                    level = LevelsFinder._create_level_from_group(current_group, level_type, df)
                    if level:
                        grouped_levels.append(level)
                
                # Начинаем новую группу
                current_group = [swing_points[i]]
        
        # Обрабатываем последнюю группу
        if current_group:
            level = LevelsFinder._create_level_from_group(current_group, level_type, df)
            if level:
                grouped_levels.append(level)
        
        return grouped_levels
    
    @staticmethod
    def _create_level_from_group(group: List[Tuple[int, float, datetime]], 
                               level_type: LevelType,
                               df: pd.DataFrame) -> Optional[PriceLevel]:
        """Создание уровня из группы swing точек"""
        try:
            # Средняя цена группы
            avg_price = sum(point[1] for point in group) / len(group)
            
            # Время первого и последнего касания
            first_touch = min(point[2] for point in group)
            last_touch = max(point[2] for point in group)
            
            # Количество касаний
            touches = len(group)
            
            # Расчет среднего объема на уровне
            volume_at_level = 0.0
            for idx, price, timestamp in group:
                if idx < len(df) and 'volume' in df.columns:
                    volume_at_level += df['volume'].iloc[idx]
            volume_at_level = volume_at_level / len(group) if group else 0.0
            
            # Расчет возраста уровня
            now = datetime.now()
            if hasattr(last_touch, 'to_pydatetime'):
                last_touch_dt = last_touch.to_pydatetime()
            else:
                last_touch_dt = last_touch
            age_days = (now - last_touch_dt).days
            
            # Определение силы уровня
            strength = LevelsFinder._calculate_level_strength(touches, volume_at_level, age_days)
            
            # Расчет уверенности
            confidence = LevelsFinder._calculate_confidence(touches, age_days, volume_at_level)
            
            return PriceLevel(
                price=avg_price,
                level_type=level_type,
                strength=strength,
                touches=touches,
                first_touch=first_touch,
                last_touch=last_touch,
                confidence=confidence,
                volume_at_level=volume_at_level,
                age_days=age_days
            )
            
        except Exception as e:
            logger.error(f"Ошибка создания уровня: {e}")
            return None
    
    @staticmethod
    def _calculate_level_strength(touches: int, volume: float, age_days: float) -> LevelStrength:
        """Расчет силы уровня"""
        score = 0
        
        # Очки за количество касаний
        if touches >= 5:
            score += 3
        elif touches >= 3:
            score += 2
        elif touches >= 2:
            score += 1
        
        # Очки за объем (если выше среднего)
        if volume > 1000:  # Примерный порог
            score += 1
        
        # Штраф за возраст
        if age_days > 60:
            score -= 1
        elif age_days > 30:
            score -= 0.5
        
        # Определение силы
        if score >= 4:
            return LevelStrength.CRITICAL
        elif score >= 3:
            return LevelStrength.STRONG
        elif score >= 1.5:
            return LevelStrength.MODERATE
        else:
            return LevelStrength.WEAK
    
    @staticmethod
    def _calculate_confidence(touches: int, age_days: float, volume: float) -> float:
        """Расчет уверенности в уровне (0-1)"""
        confidence = 0.5  # Базовая уверенность
        
        # Бонус за касания
        confidence += min(touches * 0.1, 0.3)
        
        # Бонус/штраф за возраст
        if age_days <= 7:
            confidence += 0.1  # Свежий уровень
        elif age_days > 90:
            confidence -= 0.2  # Старый уровень
        
        # Бонус за объем
        if volume > 500:
            confidence += 0.1
        
        return max(0.0, min(1.0, confidence))
    
    @staticmethod
    def find_volume_levels(df: pd.DataFrame,
                          price_levels: int = 50,
                          min_volume_pct: float = 5.0) -> List[PriceLevel]:
        """
        Поиск уровней на основе профиля объема
        
        Args:
            df: DataFrame с OHLCV данными
            price_levels: Количество ценовых уровней для анализа
            min_volume_pct: Минимальный процент объема для значимого уровня
        
        Returns:
            Список уровней на основе объема
        """
        try:
            if 'volume' not in df.columns or len(df) < 20:
                return []
            
            # Создаем ценовые диапазоны
            min_price = df['low'].min()
            max_price = df['high'].max()
            price_bins = np.linspace(min_price, max_price, price_levels + 1)
            
            # Распределяем объем по ценовым уровням
            volume_profile = np.zeros(price_levels)
            
            for i, row in df.iterrows():
                # Находим диапазон цен для текущего бара
                low_idx = np.digitize(row['low'], price_bins) - 1
                high_idx = np.digitize(row['high'], price_bins) - 1
                
                # Ограничиваем индексы
                low_idx = max(0, min(low_idx, price_levels - 1))
                high_idx = max(0, min(high_idx, price_levels - 1))
                
                # Распределяем объем
                if low_idx == high_idx:
                    volume_profile[low_idx] += row['volume']
                else:
                    volume_per_level = row['volume'] / (high_idx - low_idx + 1)
                    for level_idx in range(low_idx, high_idx + 1):
                        volume_profile[level_idx] += volume_per_level
            
            # Находим значимые уровни
            total_volume = volume_profile.sum()
            threshold_volume = total_volume * (min_volume_pct / 100)
            
            significant_levels = []
            for i, volume in enumerate(volume_profile):
                if volume >= threshold_volume:
                    price = (price_bins[i] + price_bins[i + 1]) / 2
                    volume_pct = volume / total_volume * 100
                    
                    # Определяем тип уровня (поддержка или сопротивление)
                    current_price = df['close'].iloc[-1]
                    level_type = LevelType.SUPPORT if price < current_price else LevelType.RESISTANCE
                    
                    # Создаем уровень
                    strength = LevelStrength.STRONG if volume_pct > 15 else LevelStrength.MODERATE
                    
                    level = PriceLevel(
                        price=price,
                        level_type=level_type,
                        strength=strength,
                        touches=1,  # Объемные уровни считаем как одно касание
                        first_touch=df.index[0],
                        last_touch=df.index[-1],
                        confidence=min(volume_pct / 20, 1.0),  # Чем больше объем, тем выше уверенность
                        volume_at_level=volume,
                        age_days=0
                    )
                    
                    significant_levels.append(level)
            
            # Сортировка по объему
            significant_levels.sort(key=lambda x: x.volume_at_level, reverse=True)
            
            return significant_levels
            
        except Exception as e:
            logger.error(f"Ошибка поиска объемных уровней: {e}")
            return []
    
    @staticmethod
    def find_psychological_levels(current_price: float,
                                price_range_pct: float = 10.0) -> List[PriceLevel]:
        """
        Поиск психологических уровней (круглые числа)
        
        Args:
            current_price: Текущая цена
            price_range_pct: Диапазон поиска в процентах от текущей цены
        
        Returns:
            Список психологических уровней
        """
        try:
            levels = []
            
            # Определяем диапазон поиска
            range_amount = current_price * (price_range_pct / 100)
            min_price = current_price - range_amount
            max_price = current_price + range_amount
            
            # Определяем шаг для круглых чисел на основе цены
            if current_price < 1:
                steps = [0.01, 0.05, 0.1]  # Центы
            elif current_price < 10:
                steps = [0.1, 0.5, 1.0]    # Десятые и единицы
            elif current_price < 100:
                steps = [1, 5, 10]         # Единицы и десятки
            elif current_price < 1000:
                steps = [10, 50, 100]      # Десятки и сотни
            else:
                steps = [100, 500, 1000]   # Сотни и тысячи
            
            # Находим круглые числа в диапазоне
            for step in steps:
                # Находим ближайшее круглое число снизу
                lower_round = int(min_price / step) * step
                
                # Генерируем круглые числа в диапазоне
                current_round = lower_round
                while current_round <= max_price:
                    if min_price <= current_round <= max_price and current_round != current_price:
                        # Определяем тип уровня
                        level_type = LevelType.SUPPORT if current_round < current_price else LevelType.RESISTANCE
                        
                        # Сила зависит от "круглости" числа
                        if current_round % (step * 10) == 0:  # Очень круглое число
                            strength = LevelStrength.STRONG
                            confidence = 0.8
                        elif current_round % (step * 5) == 0:  # Средне круглое
                            strength = LevelStrength.MODERATE
                            confidence = 0.6
                        else:  # Просто круглое
                            strength = LevelStrength.WEAK
                            confidence = 0.4
                        
                        level = PriceLevel(
                            price=current_round,
                            level_type=level_type,
                            strength=strength,
                            touches=0,  # Психологические уровни не имеют реальных касаний
                            first_touch=datetime.now(),
                            last_touch=datetime.now(),
                            confidence=confidence,
                            volume_at_level=0,
                            age_days=0
                        )
                        
                        levels.append(level)
                    
                    current_round += step
            
            # Убираем дубликаты и сортируем
            unique_levels = []
            seen_prices = set()
            
            for level in levels:
                if level.price not in seen_prices:
                    unique_levels.append(level)
                    seen_prices.add(level.price)
            
            unique_levels.sort(key=lambda x: abs(x.price - current_price))
            
            return unique_levels[:10]  # Возвращаем максимум 10 ближайших уровней
            
        except Exception as e:
            logger.error(f"Ошибка поиска психологических уровней: {e}")
            return []
    
    @staticmethod
    def find_fibonacci_levels(df: pd.DataFrame,
                            trend_period: int = 50) -> List[PriceLevel]:
        """
        Поиск уровней Фибоначчи
        
        Args:
            df: DataFrame с OHLC данными
            trend_period: Период для определения тренда
        
        Returns:
            Список уровней Фибоначчи
        """
        try:
            if len(df) < trend_period:
                return []
            
            # Определяем тренд за последний период
            recent_data = df.tail(trend_period)
            trend_start = recent_data.iloc[0]
            trend_end = recent_data.iloc[-1]
            
            # Находим максимум и минимум тренда
            high_price = recent_data['high'].max()
            low_price = recent_data['low'].min()
            
            # Определяем направление тренда
            is_uptrend = trend_end['close'] > trend_start['close']
            
            # Уровни Фибоначчи
            fib_levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
            
            levels = []
            
            for fib_ratio in fib_levels:
                if is_uptrend:
                    # В аптренде 0% = low, 100% = high
                    fib_price = low_price + (high_price - low_price) * fib_ratio
                    level_type = LevelType.SUPPORT if fib_ratio < 0.5 else LevelType.RESISTANCE
                else:
                    # В даунтренде 0% = high, 100% = low
                    fib_price = high_price - (high_price - low_price) * fib_ratio
                    level_type = LevelType.RESISTANCE if fib_ratio < 0.5 else LevelType.SUPPORT
                
                # Сила уровня зависит от соотношения Фибоначчи
                if fib_ratio in [0.382, 0.618]:  # Ключевые уровни
                    strength = LevelStrength.STRONG
                    confidence = 0.8
                elif fib_ratio in [0.236, 0.5, 0.786]:  # Важные уровни
                    strength = LevelStrength.MODERATE
                    confidence = 0.6
                else:  # Границы
                    strength = LevelStrength.WEAK
                    confidence = 0.4
                
                level = PriceLevel(
                    price=fib_price,
                    level_type=level_type,
                    strength=strength,
                    touches=0,
                    first_touch=recent_data.index[0],
                    last_touch=recent_data.index[-1],
                    confidence=confidence,
                    volume_at_level=0,
                    age_days=0
                )
                
                levels.append(level)
            
            return levels
            
        except Exception as e:
            logger.error(f"Ошибка поиска уровней Фибоначчи: {e}")
            return []


class LevelsAnalyzer:
    """Анализатор уровней для торговых решений"""
    
    @staticmethod
    def find_nearest_levels(levels: List[PriceLevel], 
                          current_price: float,
                          max_distance_pct: float = 2.0,
                          count: int = 5) -> Dict[str, List[PriceLevel]]:
        """
        Поиск ближайших уровней поддержки и сопротивления
        
        Args:
            levels: Список всех уровней
            current_price: Текущая цена
            max_distance_pct: Максимальное расстояние в процентах
            count: Максимальное количество уровней каждого типа
        
        Returns:
            Словарь с ближайшими уровнями поддержки и сопротивления
        """
        # Фильтруем уровни по расстоянию
        nearby_levels = [
            level for level in levels 
            if level.distance_to_price(current_price) <= max_distance_pct
        ]
        
        # Разделяем на поддержки и сопротивления
        supports = [
            level for level in nearby_levels 
            if level.price < current_price and level.level_type in [LevelType.SUPPORT, LevelType.PIVOT]
        ]
        
        resistances = [
            level for level in nearby_levels 
            if level.price > current_price and level.level_type in [LevelType.RESISTANCE, LevelType.PIVOT]
        ]
        
        # Сортируем поддержки по убыванию цены (ближайшие сверху)
        supports.sort(key=lambda x: x.price, reverse=True)
        
        # Сортируем сопротивления по возрастанию цены (ближайшие снизу)
        resistances.sort(key=lambda x: x.price)
        
        return {
            'support': supports[:count],
            'resistance': resistances[:count]
        }
    
    @staticmethod
    def calculate_level_confluence(levels: List[PriceLevel],
                                 price_tolerance_pct: float = 0.1) -> List[PriceLevel]:
        """
        Поиск зон confluence (пересечения нескольких уровней)
        
        Args:
            levels: Список уровней
            price_tolerance_pct: Толерантность для группировки уровней
        
        Returns:
            Список зон confluence
        """
        if len(levels) < 2:
            return []
        
        # Сортируем уровни по цене
        sorted_levels = sorted(levels, key=lambda x: x.price)
        
        confluence_zones = []
        current_zone = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            # Проверяем, входит ли уровень в текущую зону
            zone_avg_price = sum(l.price for l in current_zone) / len(current_zone)
            
            if abs(level.price - zone_avg_price) / zone_avg_price * 100 <= price_tolerance_pct:
                current_zone.append(level)
            else:
                # Создаем confluence зону если в ней больше одного уровня
                if len(current_zone) > 1:
                    confluence_level = LevelsAnalyzer._create_confluence_level(current_zone)
                    if confluence_level:
                        confluence_zones.append(confluence_level)
                
                # Начинаем новую зону
                current_zone = [level]
        
        # Обрабатываем последнюю зону
        if len(current_zone) > 1:
            confluence_level = LevelsAnalyzer._create_confluence_level(current_zone)
            if confluence_level:
                confluence_zones.append(confluence_level)
        
        return confluence_zones
    
    @staticmethod
    def _create_confluence_level(zone_levels: List[PriceLevel]) -> Optional[PriceLevel]:
        """Создание уровня confluence из группы уровней"""
        try:
            # Средняя цена зоны
            avg_price = sum(level.price for level in zone_levels) / len(zone_levels)
            
            # Определяем преобладающий тип
            type_counts = {}
            for level in zone_levels:
                type_counts[level.level_type] = type_counts.get(level.level_type, 0) + 1
            
            dominant_type = max(type_counts.keys(), key=lambda k: type_counts[k])
            
            # Суммарная сила
            total_touches = sum(level.touches for level in zone_levels)
            avg_confidence = sum(level.confidence for level in zone_levels) / len(zone_levels)
            
            # Определяем силу confluence зоны
            if len(zone_levels) >= 4:
                strength = LevelStrength.CRITICAL
            elif len(zone_levels) >= 3:
                strength = LevelStrength.STRONG
            else:
                strength = LevelStrength.MODERATE
            
            # Временные характеристики
            first_touch = min(level.first_touch for level in zone_levels)
            last_touch = max(level.last_touch for level in zone_levels)
            
            return PriceLevel(
                price=avg_price,
                level_type=dominant_type,
                strength=strength,
                touches=total_touches,
                first_touch=first_touch,
                last_touch=last_touch,
                confidence=min(avg_confidence * 1.2, 1.0),  # Бонус за confluence
                volume_at_level=sum(level.volume_at_level for level in zone_levels),
                age_days=min(level.age_days for level in zone_levels)
            )
            
        except Exception as e:
            logger.error(f"Ошибка создания confluence уровня: {e}")
            return None
    
    @staticmethod
    def evaluate_breakout_potential(level: PriceLevel, 
                                  current_price: float,
                                  volume: float,
                                  avg_volume: float) -> Dict[str, Union[bool, float]]:
        """
        Оценка потенциала пробоя уровня
        
        Returns:
            Словарь с оценкой пробоя
        """
        # Расстояние до уровня
        distance_pct = level.distance_to_price(current_price)
        
        # Направление приближения
        is_approaching = (
            (level.level_type == LevelType.RESISTANCE and current_price < level.price) or
            (level.level_type == LevelType.SUPPORT and current_price > level.price)
        )
        
        # Оценка объема
        volume_factor = volume / avg_volume if avg_volume > 0 else 1.0
        high_volume = volume_factor > 1.5
        
        # Возраст уровня
        is_fresh = level.age_days < 30
        
        # Сила уровня (обратная логика - слабые уровни пробиваются легче)
        is_weak = level.strength == LevelStrength.WEAK
        
        # Итоговая оценка пробоя
        breakout_score = 0.0
        
        if is_approaching:
            breakout_score += 0.3
        
        if high_volume:
            breakout_score += 0.3
        
        if is_weak:
            breakout_score += 0.2
        
        if distance_pct < 0.5:  # Очень близко к уровню
            breakout_score += 0.2
        
        # Штраф за сильный уровень
        if level.strength == LevelStrength.CRITICAL:
            breakout_score -= 0.3
        elif level.strength == LevelStrength.STRONG:
            breakout_score -= 0.1
        
        breakout_likely = breakout_score > 0.5
        
        return {
            'breakout_likely': breakout_likely,
            'breakout_score': max(0.0, min(1.0, breakout_score)),
            'distance_pct': distance_pct,
            'is_approaching': is_approaching,
            'high_volume': high_volume,
            'volume_factor': volume_factor,
            'level_strength': level.strength.value
        }


# =========================================================================
# УТИЛИТНЫЕ ФУНКЦИИ
# =========================================================================

def find_all_levels(df: pd.DataFrame, 
                   current_price: Optional[float] = None,
                   include_psychological: bool = True,
                   include_fibonacci: bool = True,
                   include_volume: bool = True) -> List[PriceLevel]:
    """
    Поиск всех типов уровней
    
    Args:
        df: DataFrame с OHLCV данными
        current_price: Текущая цена (если None, берется последняя цена закрытия)
        include_psychological: Включить психологические уровни
        include_fibonacci: Включить уровни Фибоначчи
        include_volume: Включить объемные уровни
    
    Returns:
        Объединенный список всех найденных уровней
    """
    if current_price is None:
        current_price = df['close'].iloc[-1]
    
    all_levels = []
    
    # Swing уровни (всегда включены)
    swing_levels = LevelsFinder.find_swing_levels(df)
    all_levels.extend(swing_levels)
    
    # Психологические уровни
    if include_psychological:
        psych_levels = LevelsFinder.find_psychological_levels(current_price)
        all_levels.extend(psych_levels)
    
    # Уровни Фибоначчи
    if include_fibonacci:
        fib_levels = LevelsFinder.find_fibonacci_levels(df)
        all_levels.extend(fib_levels)
    
    # Объемные уровни
    if include_volume and 'volume' in df.columns:
        volume_levels = LevelsFinder.find_volume_levels(df)
        all_levels.extend(volume_levels)
    
    # Убираем дубликаты по цене (с толерантностью)
    unique_levels = []
    tolerance = 0.1  # 0.1%
    
    for level in all_levels:
        is_duplicate = False
        for existing in unique_levels:
            if abs(level.price - existing.price) / existing.price * 100 < tolerance:
                # Оставляем уровень с большей уверенностью
                if level.confidence > existing.confidence:
                    unique_levels.remove(existing)
                    unique_levels.append(level)
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_levels.append(level)
    
    # Сортируем по расстоянию от текущей цены
    unique_levels.sort(key=lambda x: x.distance_to_price(current_price))
    
    return unique_levels


def get_trading_levels(df: pd.DataFrame, 
                      current_price: Optional[float] = None,
                      max_levels: int = 10) -> Dict[str, List[PriceLevel]]:
    """
    Получение ключевых торговых уровней
    
    Returns:
        Словарь с ключевыми уровнями для торговли
    """
    if current_price is None:
        current_price = df['close'].iloc[-1]
    
    # Находим все уровни
    all_levels = find_all_levels(df, current_price)
    
    # Анализируем ближайшие уровни
    nearby_levels = LevelsAnalyzer.find_nearest_levels(all_levels, current_price)
    
    # Ищем зоны confluence
    confluence_zones = LevelsAnalyzer.calculate_level_confluence(all_levels)
    
    # Фильтруем только надежные уровни
    reliable_levels = [level for level in all_levels if level.is_reliable]
    
    return {
        'nearest_support': nearby_levels.get('support', [])[:max_levels//2],
        'nearest_resistance': nearby_levels.get('resistance', [])[:max_levels//2],
        'confluence_zones': confluence_zones[:5],
        'reliable_levels': reliable_levels[:max_levels],
        'all_levels': all_levels[:max_levels*2]
    }


# =========================================================================
# КОНСТАНТЫ
# =========================================================================

# Настройки по умолчанию для разных типов анализа
DEFAULT_SWING_PARAMS = {
    'lookback': 20,
    'min_touches': 2,
    'tolerance_pct': 0.1
}

DEFAULT_VOLUME_PARAMS = {
    'price_levels': 50,
    'min_volume_pct': 5.0
}

DEFAULT_FIBONACCI_PARAMS = {
    'trend_period': 50
}

# Важные уровни Фибоначчи
FIBONACCI_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
KEY_FIBONACCI_LEVELS = [0.382, 0.5, 0.618]