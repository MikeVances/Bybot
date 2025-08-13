# bot/ai/neural_integration.py
# Интеграция нейронной сети с торговым ботом и риск-менеджментом
# Функции: анализ стратегий, управление ставками, интеграция с риск-менеджером

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import json
import os
from .neural_trader import NeuralTrader

class NeuralIntegration:
    """
    Улучшенная интеграция нейронной сети с торговым ботом
    
    Новые возможности:
    - Интеграция с риск-менеджером
    - Расширенный анализ стратегий
    - Автоматическое обучение на реальных результатах
    - Адаптивные пороги уверенности
    - Мониторинг качества предсказаний
    """
    
    def __init__(self, risk_manager=None):
        # Инициализация нейронной сети
        self.neural_trader = NeuralTrader()
        self.risk_manager = risk_manager
        self.logger = logging.getLogger('neural_integration')
        
        # Отслеживание ставок и сделок
        self.active_bets = {}  # {bet_id: bet_info}
        self.completed_trades = []  # История завершенных сделок
        self.strategy_performance_cache = {}  # Кеш анализа стратегий
        
        # Параметры анализа
        self.profit_threshold = 0.5  # Минимальная прибыль для успешной сделки (%)
        self.timeout_hours = 24  # Таймаут для анализа сделки
        self.cache_ttl_minutes = 15  # TTL кеша анализа стратегий
        
        # Настройки интеграции с риск-менеджером
        self.risk_integration_enabled = risk_manager is not None
        self.max_neural_exposure_pct = 10.0  # Максимальная экспозиция нейронных ставок
        self.neural_position_limit = 3  # Максимум нейронных позиций одновременно
        
        # Метрики качества
        self.prediction_accuracy_history = []
        self.confidence_calibration_history = []
        self.last_performance_check = datetime.now()
        
        # Автоматическое обучение
        self.auto_learning_enabled = True
        self.learning_frequency_hours = 6  # Частота переобучения
        self.min_samples_for_learning = 20
        
        # Динамический маппинг стратегий
        self.strategy_mapping = {}
        self.reverse_strategy_mapping = {}
        self.active_strategies_file = "bot/strategy/active_strategies.txt"
        self.max_neural_strategies = 10  # Максимальное количество стратегий для нейромодуля
        
        # Загружаем активные стратегии
        self._load_active_strategies()
        
        # Отслеживание изменений файла стратегий
        self.last_file_check = datetime.now()
        self.file_check_interval = 300  # Проверяем каждые 5 минут
        self.last_file_mtime = 0
    
    def _check_strategies_file_changes(self) -> bool:
        """Проверка изменений в файле активных стратегий"""
        try:
            current_time = datetime.now()
            
            # Проверяем интервал проверки
            if (current_time - self.last_file_check).total_seconds() < self.file_check_interval:
                return False
            
            if not os.path.exists(self.active_strategies_file):
                return False
            
            # Проверяем время модификации файла
            current_mtime = os.path.getmtime(self.active_strategies_file)
            
            if current_mtime > self.last_file_mtime:
                self.logger.info("Обнаружены изменения в файле активных стратегий")
                self.last_file_mtime = current_mtime
                self.last_file_check = current_time
                return True
            
            self.last_file_check = current_time
            return False
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки изменений файла стратегий: {e}")
            return False
    
    def _load_active_strategies(self):
        """Динамическая загрузка активных стратегий из файла"""
        try:
            if not os.path.exists(self.active_strategies_file):
                self.logger.warning(f"Файл активных стратегий не найден: {self.active_strategies_file}")
                return
            
            with open(self.active_strategies_file, 'r') as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            if not lines:
                self.logger.warning("Файл активных стратегий пуст")
                return
            
            # Очищаем старые маппинги
            self.strategy_mapping.clear()
            self.reverse_strategy_mapping.clear()
            
            # Создаем маппинг для активных стратегий
            for i, strategy_name in enumerate(lines[:self.max_neural_strategies], 1):
                neural_name = f'strategy_{i:02d}'
                self.strategy_mapping[strategy_name] = neural_name
                self.reverse_strategy_mapping[neural_name] = strategy_name
            
            self.logger.info(f"Загружено {len(self.strategy_mapping)} активных стратегий для нейромодуля")
            self.logger.debug(f"Маппинг стратегий: {self.strategy_mapping}")
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки активных стратегий: {e}")
    
    def reload_active_strategies(self):
        """Перезагрузка активных стратегий (для динамического обновления)"""
        self._load_active_strategies()
        self.logger.info("Активные стратегии перезагружены")
    
    def get_active_strategies_info(self) -> Dict:
        """Получение информации о загруженных стратегиях"""
        return {
            'total_strategies': len(self.strategy_mapping),
            'active_strategies': list(self.strategy_mapping.keys()),
            'neural_mapping': self.strategy_mapping,
            'max_strategies': self.max_neural_strategies
        }
    
    def get_dynamic_strategies_stats(self) -> Dict:
        """Получение расширенной статистики по динамическим стратегиям"""
        try:
            # Проверяем изменения в файле
            file_changed = self._check_strategies_file_changes()
            
            stats = {
                'total_strategies': len(self.strategy_mapping),
                'active_strategies': list(self.strategy_mapping.keys()),
                'neural_mapping': self.strategy_mapping,
                'max_strategies': self.max_neural_strategies,
                'file_last_modified': None,
                'file_changed': file_changed,
                'last_check': self.last_file_check.isoformat(),
                'check_interval_seconds': self.file_check_interval
            }
            
            # Добавляем информацию о файле
            if os.path.exists(self.active_strategies_file):
                stats['file_last_modified'] = datetime.fromtimestamp(
                    os.path.getmtime(self.active_strategies_file)
                ).isoformat()
                stats['file_exists'] = True
            else:
                stats['file_exists'] = False
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики стратегий: {e}")
            return {
                'error': str(e),
                'total_strategies': 0,
                'active_strategies': [],
                'neural_mapping': {}
            }
    
    def adapt_strategy_signals_for_neural(self, strategy_signals: Dict) -> Dict:
        """
        Адаптация сигналов стратегий новой архитектуры к формату нейромодуля
        
        Args:
            strategy_signals: Сигналы от новых стратегий
            
        Returns:
            Адаптированные сигналы для нейромодуля
        """
        adapted_signals = {}
        
        for strategy_name, signal_data in strategy_signals.items():
            if strategy_name in self.strategy_mapping:
                neural_strategy_name = self.strategy_mapping[strategy_name]
                adapted_signals[neural_strategy_name] = signal_data
            else:
                # Если стратегия не в маппинге, используем оригинальное имя
                self.logger.warning(f"Стратегия {strategy_name} не найдена в маппинге")
                adapted_signals[strategy_name] = signal_data
        
        return adapted_signals
    
    def adapt_neural_recommendation(self, neural_recommendation: Dict) -> Dict:
        """
        Адаптация рекомендации нейромодуля к названиям стратегий новой архитектуры
        
        Args:
            neural_recommendation: Рекомендация от нейромодуля
            
        Returns:
            Адаптированная рекомендация
        """
        if not neural_recommendation:
            return None
            
        strategy_name = neural_recommendation.get('strategy', '')
        
        if strategy_name in self.reverse_strategy_mapping:
            adapted_recommendation = neural_recommendation.copy()
            adapted_recommendation['strategy'] = self.reverse_strategy_mapping[strategy_name]
            return adapted_recommendation
        else:
            # Если стратегия не в обратном маппинге, возвращаем как есть
            return neural_recommendation
    
    def analyze_strategy_results(self, trade_journal_path: str = "data/trade_journal.csv") -> Dict:
        """Расширенный анализ результатов стратегий с кешированием"""
        try:
            # Проверяем кеш
            current_time = datetime.now()
            cache_key = f"strategy_analysis_{trade_journal_path}"
            
            if (cache_key in self.strategy_performance_cache and 
                (current_time - self.strategy_performance_cache[cache_key]['timestamp']).total_seconds() < self.cache_ttl_minutes * 60):
                return self.strategy_performance_cache[cache_key]['data']
            
            # Проверяем существование файла
            if not os.path.exists(trade_journal_path):
                self.logger.warning(f"Файл журнала сделок не найден: {trade_journal_path}")
                return {}
            
            df = pd.read_csv(trade_journal_path)
            if df.empty:
                self.logger.info("Журнал сделок пуст")
                return {}
            
            # Конвертируем timestamp в datetime для анализа с обработкой ошибок
            if 'timestamp' in df.columns:
                try:
                    # Пробуем разные форматы timestamp
                    if df['timestamp'].dtype == 'object':
                        # Проверяем, можно ли конвертировать в datetime
                        sample_timestamp = df['timestamp'].iloc[0]
                        if isinstance(sample_timestamp, str) and len(sample_timestamp) < 10:
                            # Скорее всего это неправильный формат, пропускаем анализ
                            self.logger.warning(f"Неправильный формат timestamp в журнале сделок: {sample_timestamp}")
                            return {}
                    
                    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                    # Удаляем строки с неправильными датами
                    df = df.dropna(subset=['timestamp'])
                    
                    if df.empty:
                        self.logger.warning("Все записи в журнале сделок имеют неправильные даты")
                        return {}
                        
                except Exception as e:
                    self.logger.warning(f"Ошибка конвертации timestamp: {e}")
                    return {}
                
                df = df.sort_values('timestamp')
            
            strategy_results = {}
            
            for strategy_name in df['strategy'].unique():
                if pd.isna(strategy_name):
                    continue
                    
                strategy_df = df[df['strategy'] == strategy_name].copy()
                
                # Базовая статистика
                total_signals = len(strategy_df)
                buy_signals = len(strategy_df[strategy_df['signal'] == 'BUY'])
                sell_signals = len(strategy_df[strategy_df['signal'] == 'SELL'])
                
                # Анализ временных паттернов
                time_analysis = self._analyze_time_patterns(strategy_df)
                
                # Анализ производительности по ценам
                price_analysis = self._analyze_price_performance_advanced(strategy_df)
                
                # Анализ качества сигналов
                signal_quality = self._analyze_signal_quality(strategy_df)
                
                # Анализ корреляции с рынком
                market_correlation = self._analyze_market_correlation(strategy_df)
                
                # Риск-метрики
                risk_metrics = self._calculate_strategy_risk_metrics(strategy_df)
                
                strategy_results[strategy_name] = {
                    'basic_stats': {
                        'total_signals': total_signals,
                        'buy_signals': buy_signals,
                        'sell_signals': sell_signals
                    },
                    'time_analysis': time_analysis,
                    'price_analysis': price_analysis,
                    'signal_quality': signal_quality,
                    'market_correlation': market_correlation,
                    'risk_metrics': risk_metrics,
                    'signal_frequency': self._calculate_signal_frequency(strategy_df)
                }
                
                # Добавляем последний сигнал
                if not strategy_df.empty:
                    strategy_results[strategy_name]['last_signal'] = strategy_df.iloc[-1].to_dict()
            
            # Кешируем результаты
            self.strategy_performance_cache[cache_key] = {
                'data': strategy_results,
                'timestamp': current_time
            }
            
            return strategy_results
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа результатов стратегий: {e}")
            return {}
    
    def _analyze_time_patterns(self, strategy_df: pd.DataFrame) -> Dict:
        """Анализ временных паттернов стратегии"""
        try:
            if 'timestamp' not in strategy_df.columns or strategy_df.empty:
                return {}
            
            # Анализ по часам дня
            strategy_df['hour'] = strategy_df['timestamp'].dt.hour
            hourly_stats = strategy_df.groupby('hour').size().to_dict()
            
            # Анализ по дням недели
            strategy_df['weekday'] = strategy_df['timestamp'].dt.weekday
            weekday_stats = strategy_df.groupby('weekday').size().to_dict()
            
            # Активность в последние дни
            recent_days = 7
            cutoff_date = datetime.now() - timedelta(days=recent_days)
            recent_activity = len(strategy_df[strategy_df['timestamp'] > cutoff_date])
            
            return {
                'hourly_distribution': hourly_stats,
                'weekday_distribution': weekday_stats,
                'recent_activity': recent_activity,
                'most_active_hour': max(hourly_stats.items(), key=lambda x: x[1])[0] if hourly_stats else None,
                'least_active_hour': min(hourly_stats.items(), key=lambda x: x[1])[0] if hourly_stats else None
            }
        except Exception as e:
            self.logger.error(f"Ошибка анализа временных паттернов: {e}")
            return {}
    
    def _analyze_price_performance_advanced(self, strategy_df: pd.DataFrame) -> Dict:
        """Расширенный анализ производительности по ценам"""
        try:
            # Используем последние сигналы для анализа
            analysis_window = min(200, len(strategy_df))  # Увеличиваем окно анализа
            recent_df = strategy_df.tail(analysis_window).copy()
            
            if recent_df.empty:
                return {'success_rate': 0.5, 'avg_profit': 0, 'total_trades': 0}
            
            # Конвертируем цены в числовой формат
            price_columns = ['entry_price', 'close', 'stop_loss', 'take_profit']
            for col in price_columns:
                if col in recent_df.columns:
                    recent_df[col] = pd.to_numeric(recent_df[col], errors='coerce')
            
            success_count = 0
            total_profit = 0
            profitable_trades = []
            losing_trades = []
            
            for _, row in recent_df.iterrows():
                entry_price = row.get('entry_price', 0)
                close_price = row.get('close', 0)
                
                if entry_price > 0 and close_price > 0:
                    # Расчет прибыли в зависимости от типа сигнала
                    if row['signal'] == 'BUY':
                        profit_pct = (close_price - entry_price) / entry_price * 100
                    elif row['signal'] == 'SELL':
                        profit_pct = (entry_price - close_price) / entry_price * 100
                    else:
                        continue
                    
                    total_profit += profit_pct
                    
                    if profit_pct > self.profit_threshold:
                        success_count += 1
                        profitable_trades.append(profit_pct)
                    else:
                        losing_trades.append(profit_pct)
            
            total_analyzed = len([row for _, row in recent_df.iterrows() 
                                if row.get('entry_price', 0) > 0 and row.get('close', 0) > 0])
            
            if total_analyzed == 0:
                return {'success_rate': 0.5, 'avg_profit': 0, 'total_trades': 0}
            
            success_rate = success_count / total_analyzed
            avg_profit = total_profit / total_analyzed
            
            # Дополнительные метрики
            max_profit = max(profitable_trades) if profitable_trades else 0
            max_loss = min(losing_trades) if losing_trades else 0
            avg_winning_trade = np.mean(profitable_trades) if profitable_trades else 0
            avg_losing_trade = np.mean(losing_trades) if losing_trades else 0
            
            # Коэффициент прибыльности
            profit_factor = (abs(avg_winning_trade) * len(profitable_trades) / 
                           (abs(avg_losing_trade) * len(losing_trades))) if losing_trades else float('inf')
            
            return {
                'success_rate': success_rate,
                'avg_profit': avg_profit,
                'total_trades': total_analyzed,
                'profitable_trades': len(profitable_trades),
                'losing_trades': len(losing_trades),
                'max_profit': max_profit,
                'max_loss': max_loss,
                'avg_winning_trade': avg_winning_trade,
                'avg_losing_trade': avg_losing_trade,
                'profit_factor': min(profit_factor, 10.0),  # Ограничиваем для стабильности
                'win_rate': success_rate * 100,
                'expectancy': avg_profit
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа производительности: {e}")
            return {'success_rate': 0.5, 'avg_profit': 0, 'total_trades': 0}
    
    def _analyze_signal_quality(self, strategy_df: pd.DataFrame) -> Dict:
        """Анализ качества сигналов стратегии"""
        try:
            if strategy_df.empty:
                return {}
            
            # Анализ R:R соотношений
            rr_ratios = []
            signal_strengths = []
            
            for _, row in strategy_df.iterrows():
                if 'risk_reward_ratio' in row and pd.notna(row['risk_reward_ratio']):
                    rr_ratios.append(float(row['risk_reward_ratio']))
                
                if 'signal_strength' in row and pd.notna(row['signal_strength']):
                    signal_strengths.append(float(row['signal_strength']))
            
            quality_metrics = {
                'avg_rr_ratio': np.mean(rr_ratios) if rr_ratios else 1.0,
                'min_rr_ratio': min(rr_ratios) if rr_ratios else 0,
                'max_rr_ratio': max(rr_ratios) if rr_ratios else 0,
                'avg_signal_strength': np.mean(signal_strengths) if signal_strengths else 0.5,
                'signal_consistency': 1 - np.std(signal_strengths) if len(signal_strengths) > 1 else 0.5,
                'quality_score': 0.5  # Базовая оценка
            }
            
            # Расчет общей оценки качества
            if rr_ratios and signal_strengths:
                rr_score = min(np.mean(rr_ratios) / 2.0, 1.0)  # Нормализуем к 1.0
                strength_score = np.mean(signal_strengths)
                consistency_score = quality_metrics['signal_consistency']
                
                quality_metrics['quality_score'] = (rr_score * 0.4 + strength_score * 0.4 + consistency_score * 0.2)
            
            return quality_metrics
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа качества сигналов: {e}")
            return {'quality_score': 0.5}
    
    def _analyze_market_correlation(self, strategy_df: pd.DataFrame) -> Dict:
        """Анализ корреляции стратегии с рыночными условиями"""
        try:
            if strategy_df.empty or 'close' not in strategy_df.columns:
                return {}
            
            # Анализ производительности в разных рыночных условиях
            strategy_df['price_change'] = strategy_df['close'].pct_change()
            
            # Классификация рыночных условий
            bullish_threshold = 0.01  # 1% рост
            bearish_threshold = -0.01  # 1% падение
            
            bullish_signals = strategy_df[strategy_df['price_change'] > bullish_threshold]
            bearish_signals = strategy_df[strategy_df['price_change'] < bearish_threshold]
            sideways_signals = strategy_df[
                (strategy_df['price_change'] >= bearish_threshold) & 
                (strategy_df['price_change'] <= bullish_threshold)
            ]
            
            return {
                'bullish_performance': {
                    'signal_count': len(bullish_signals),
                    'buy_ratio': len(bullish_signals[bullish_signals['signal'] == 'BUY']) / len(bullish_signals) if len(bullish_signals) > 0 else 0
                },
                'bearish_performance': {
                    'signal_count': len(bearish_signals),
                    'sell_ratio': len(bearish_signals[bearish_signals['signal'] == 'SELL']) / len(bearish_signals) if len(bearish_signals) > 0 else 0
                },
                'sideways_performance': {
                    'signal_count': len(sideways_signals),
                    'signal_distribution': len(sideways_signals) / len(strategy_df) if len(strategy_df) > 0 else 0
                },
                'market_adaptability': self._calculate_market_adaptability(strategy_df)
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа корреляции с рынком: {e}")
            return {}
    
    def _calculate_market_adaptability(self, strategy_df: pd.DataFrame) -> float:
        """Расчет адаптивности стратегии к рыночным условиям"""
        try:
            if len(strategy_df) < 10:
                return 0.5
            
            # Анализ изменчивости в сигналах
            signal_changes = 0
            prev_signal = None
            
            for _, row in strategy_df.iterrows():
                current_signal = row['signal']
                if prev_signal and current_signal != prev_signal:
                    signal_changes += 1
                prev_signal = current_signal
            
            # Нормализуем к диапазону 0-1
            adaptability = min(signal_changes / len(strategy_df), 1.0)
            return adaptability
            
        except:
            return 0.5
    
    def _calculate_strategy_risk_metrics(self, strategy_df: pd.DataFrame) -> Dict:
        """Расчет риск-метрик стратегии"""
        try:
            if strategy_df.empty:
                return {}
            
            # Частота сигналов
            signal_frequency = self._calculate_signal_frequency(strategy_df)
            
            # Анализ концентрации сигналов во времени
            time_concentration = self._calculate_time_concentration(strategy_df)
            
            # Оценка стабильности
            stability_score = self._calculate_stability_score(strategy_df)
            
            return {
                'signal_frequency': signal_frequency,
                'time_concentration': time_concentration,
                'stability_score': stability_score,
                'risk_level': self._assess_risk_level(signal_frequency, time_concentration, stability_score)
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета риск-метрик: {e}")
            return {}
    
    def _calculate_signal_frequency(self, strategy_df: pd.DataFrame) -> float:
        """Расчет частоты сигналов (сигналов в день)"""
        try:
            if 'timestamp' not in strategy_df.columns or strategy_df.empty:
                return 0.0
            
            # Временной диапазон данных
            time_span = (strategy_df['timestamp'].max() - strategy_df['timestamp'].min()).total_seconds()
            days = max(time_span / (24 * 3600), 1)  # Минимум 1 день
            
            return len(strategy_df) / days
            
        except:
            return 0.0
    
    def _calculate_time_concentration(self, strategy_df: pd.DataFrame) -> float:
        """Расчет концентрации сигналов во времени"""
        try:
            if 'timestamp' not in strategy_df.columns or len(strategy_df) < 2:
                return 0.5
            
            # Интервалы между сигналами
            time_diffs = strategy_df['timestamp'].diff().dt.total_seconds().dropna()
            
            if len(time_diffs) == 0:
                return 0.5
            
            # Коэффициент вариации временных интервалов
            cv = np.std(time_diffs) / np.mean(time_diffs) if np.mean(time_diffs) > 0 else 0
            
            # Нормализуем к диапазону 0-1 (высокая концентрация = высокий риск)
            return min(cv / 2.0, 1.0)
            
        except:
            return 0.5
    
    def _calculate_stability_score(self, strategy_df: pd.DataFrame) -> float:
        """Расчет оценки стабильности стратегии"""
        try:
            if strategy_df.empty:
                return 0.5
            
            # Анализ изменчивости в результатах
            recent_window = min(50, len(strategy_df))
            recent_data = strategy_df.tail(recent_window)
            
            # Подсчет успешных периодов
            success_periods = 0
            window_size = 10
            
            for i in range(0, len(recent_data) - window_size + 1, window_size):
                window_data = recent_data.iloc[i:i+window_size]
                # Простая оценка: если больше BUY сигналов в растущем рынке
                buy_signals = len(window_data[window_data['signal'] == 'BUY'])
                if buy_signals >= window_size // 2:
                    success_periods += 1
            
            total_periods = max((len(recent_data) // window_size), 1)
            stability = success_periods / total_periods
            
            return stability
            
        except:
            return 0.5
    
    def _assess_risk_level(self, frequency: float, concentration: float, stability: float) -> str:
        """Оценка общего уровня риска стратегии"""
        try:
            # Взвешенная оценка риска
            risk_score = (frequency * 0.3 + concentration * 0.4 + (1 - stability) * 0.3)
            
            if risk_score < 0.3:
                return "low"
            elif risk_score < 0.6:
                return "medium"
            else:
                return "high"
                
        except:
            return "medium"
    
    def make_neural_recommendation(self, market_data: Dict, strategy_signals: Dict) -> Optional[Dict]:
        """Улучшенное получение рекомендации с интеграцией риск-менеджмента"""
        try:
            # Проверяем интеграцию с риск-менеджером
            if self.risk_integration_enabled and self.risk_manager:
                # Проверяем лимиты нейронных позиций
                neural_positions = len([bet for bet in self.active_bets.values() 
                                      if bet.get('type') == 'neural_position'])
                
                if neural_positions >= self.neural_position_limit:
                    self.logger.info("Достигнут лимит нейронных позиций")
                    return None
                
                # Проверяем общую экспозицию
                total_exposure = sum([bet.get('bet_amount', 0) for bet in self.active_bets.values()])
                risk_report = self.risk_manager.get_risk_report()
                current_balance = risk_report.get('total_exposure', 1000)
                
                if total_exposure / current_balance > self.max_neural_exposure_pct / 100:
                    self.logger.info(f"Превышен лимит нейронной экспозиции: {total_exposure/current_balance*100:.1f}%")
                    return None
            
            # Проверяем изменения в файле активных стратегий
            if self._check_strategies_file_changes():
                self.logger.info("Перезагружаем активные стратегии из-за изменений в файле")
                self._load_active_strategies()
            
            # Проверяем, нужно ли перезагрузить активные стратегии
            if not self.strategy_mapping:
                self.logger.info("Маппинг стратегий пуст, перезагружаем активные стратегии")
                self._load_active_strategies()
            
            # Анализируем результаты стратегий
            strategy_results = self.analyze_strategy_results()
            
            # Адаптируем сигналы стратегий для нейромодуля
            adapted_signals = self.adapt_strategy_signals_for_neural(strategy_signals)
            
            # Получаем предсказания от нейронной сети
            predictions = self.neural_trader.predict_strategy_performance(market_data, adapted_signals)
            
            if not predictions:
                return None
            
            # Комбинируем нейронные предсказания с историческими данными
            combined_recommendations = {}
            
            for strategy_name, neural_score in predictions.items():
                # Адаптируем название стратегии обратно для анализа
                original_strategy_name = self.reverse_strategy_mapping.get(strategy_name, strategy_name)
                strategy_stats = strategy_results.get(original_strategy_name, {})
                historical_data = strategy_stats.get('performance', {})
                
                historical_score = historical_data.get('success_rate', 0.5)
                quality_score = strategy_stats.get('signal_quality', {}).get('quality_score', 0.5)
                risk_level = strategy_stats.get('risk_metrics', {}).get('risk_level', 'medium')
                
                # Адаптивные веса на основе качества данных
                neural_weight = 0.7
                historical_weight = 0.2
                quality_weight = 0.1
                
                # Корректируем веса на основе количества исторических данных
                total_trades = historical_data.get('total_trades', 0)
                if total_trades < 10:
                    neural_weight = 0.8
                    historical_weight = 0.1
                    quality_weight = 0.1
                elif total_trades > 100:
                    neural_weight = 0.6
                    historical_weight = 0.3
                    quality_weight = 0.1
                
                # Взвешенная комбинированная оценка
                combined_score = (neural_weight * neural_score + 
                                historical_weight * historical_score + 
                                quality_weight * quality_score)
                
                # Применяем штраф за высокий риск
                risk_multiplier = {'low': 1.0, 'medium': 0.95, 'high': 0.85}.get(risk_level, 0.9)
                combined_score *= risk_multiplier
                
                combined_recommendations[strategy_name] = {
                    'neural_score': neural_score,
                    'historical_score': historical_score,
                    'quality_score': quality_score,
                    'combined_score': combined_score,
                    'risk_level': risk_level,
                    'total_signals': strategy_stats.get('basic_stats', {}).get('total_signals', 0),
                    'success_rate': historical_score,
                    'profit_factor': historical_data.get('profit_factor', 1.0),
                    'weights_used': {
                        'neural': neural_weight,
                        'historical': historical_weight,
                        'quality': quality_weight
                    }
                }
            
            if not combined_recommendations:
                return None
            
            # Находим лучшую стратегию
            best_strategy = max(combined_recommendations.items(), key=lambda x: x[1]['combined_score'])
            
            # Адаптивный порог уверенности
            dynamic_threshold = self._calculate_adaptive_threshold(combined_recommendations)
            
            if best_strategy[1]['combined_score'] > dynamic_threshold:
                # Адаптируем название стратегии обратно для возврата
                original_strategy_name = self.reverse_strategy_mapping.get(best_strategy[0], best_strategy[0])
                recommendation = {
                    'strategy': original_strategy_name,
                    'confidence': best_strategy[1]['combined_score'],
                    'neural_score': best_strategy[1]['neural_score'],
                    'historical_score': best_strategy[1]['historical_score'],
                    'quality_score': best_strategy[1]['quality_score'],
                    'risk_level': best_strategy[1]['risk_level'],
                    'total_signals': best_strategy[1]['total_signals'],
                    'success_rate': best_strategy[1]['success_rate'],
                    'profit_factor': best_strategy[1]['profit_factor'],
                    'threshold_used': dynamic_threshold,
                    'timestamp': datetime.now().isoformat(),
                    'all_recommendations': combined_recommendations,
                    'market_conditions': self._assess_current_market_conditions(market_data)
                }
                
                self.logger.info(f"Нейронная рекомендация: {best_strategy[0]} "
                               f"(уверенность: {best_strategy[1]['combined_score']:.3f}, "
                               f"риск: {best_strategy[1]['risk_level']})")
                
                # Обновляем историю точности предсказаний
                self._update_prediction_accuracy(recommendation)
                
                return recommendation
            else:
                self.logger.debug(f"Лучшая уверенность {best_strategy[1]['combined_score']:.3f} "
                                f"ниже порога {dynamic_threshold:.3f}")
                return None
            
        except Exception as e:
            self.logger.error(f"Ошибка получения нейронной рекомендации: {e}")
            return None
    
    def _calculate_adaptive_threshold(self, recommendations: Dict) -> float:
        """Расчет адаптивного порога уверенности"""
        try:
            # Базовый порог
            base_threshold = 0.6
            
            # Анализируем качество доступных рекомендаций
            scores = [rec['combined_score'] for rec in recommendations.values()]
            if not scores:
                return base_threshold
            
            max_score = max(scores)
            avg_score = np.mean(scores)
            score_std = np.std(scores)
            
            # Если все рекомендации слабые, снижаем порог
            if max_score < 0.55:
                adaptive_threshold = base_threshold - 0.05
            # Если есть очень сильные рекомендации, повышаем порог
            elif max_score > 0.8 and score_std > 0.1:
                adaptive_threshold = base_threshold + 0.05
            else:
                adaptive_threshold = base_threshold
            
            # Учитываем историческую производительность нейронной сети
            neural_stats = self.neural_trader.get_statistics()
            win_rate = neural_stats.get('win_rate', 50) / 100
            
            if win_rate > 0.6:
                adaptive_threshold -= 0.05  # Более либеральный порог при хорошей производительности
            elif win_rate < 0.4:
                adaptive_threshold += 0.05  # Более строгий порог при плохой производительности
            
            return np.clip(adaptive_threshold, 0.5, 0.8)
            
        except:
            return 0.6
    
    def _assess_current_market_conditions(self, market_data: Dict) -> Dict:
        """Оценка текущих рыночных условий"""
        try:
            conditions = {
                'volatility': 'medium',
                'trend': 'sideways',
                'volume': 'normal',
                'risk_level': 'medium'
            }
            
            # Анализ волатильности
            for tf in ['5m', '15m', '1h']:
                if tf in market_data and market_data[tf] is not None and not market_data[tf].empty:
                    df = market_data[tf].tail(20)
                    if len(df) > 1:
                        returns = df['close'].pct_change().dropna()
                        if len(returns) > 0:
                            volatility = returns.std()
                            
                            if volatility > 0.02:  # 2%
                                conditions['volatility'] = 'high'
                            elif volatility < 0.01:  # 1%
                                conditions['volatility'] = 'low'
                            
                            # Анализ тренда
                            price_change = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]
                            if price_change > 0.01:  # 1%
                                conditions['trend'] = 'bullish'
                            elif price_change < -0.01:  # -1%
                                conditions['trend'] = 'bearish'
                            
                            # Анализ объема
                            volume_avg = df['volume'].mean()
                            volume_current = df['volume'].iloc[-1]
                            if volume_current > volume_avg * 1.5:
                                conditions['volume'] = 'high'
                            elif volume_current < volume_avg * 0.7:
                                conditions['volume'] = 'low'
                            
                            break
            
            # Общий уровень риска
            risk_factors = 0
            if conditions['volatility'] == 'high':
                risk_factors += 1
            if conditions['volume'] == 'low':
                risk_factors += 1
            
            if risk_factors >= 2:
                conditions['risk_level'] = 'high'
            elif risk_factors == 1:
                conditions['risk_level'] = 'medium'
            else:
                conditions['risk_level'] = 'low'
            
            return conditions
            
        except:
            return {'volatility': 'medium', 'trend': 'sideways', 'volume': 'normal', 'risk_level': 'medium'}
    
    def _update_prediction_accuracy(self, recommendation: Dict):
        """Обновление истории точности предсказаний"""
        try:
            self.prediction_accuracy_history.append({
                'timestamp': datetime.now().isoformat(),
                'strategy': recommendation['strategy'],
                'confidence': recommendation['confidence'],
                'neural_score': recommendation['neural_score'],
                'historical_score': recommendation['historical_score']
            })
            
            # Ограничиваем историю
            if len(self.prediction_accuracy_history) > 1000:
                self.prediction_accuracy_history = self.prediction_accuracy_history[-1000:]
                
        except Exception as e:
            self.logger.error(f"Ошибка обновления истории точности: {e}")
    
    def place_neural_bet(self, market_data: Dict, strategy_signals: Dict) -> Optional[Dict]:
        """Размещение нейронной ставки с улучшенным контролем"""
        try:
            # Получаем рекомендацию
            recommendation = self.make_neural_recommendation(market_data, strategy_signals)
            if not recommendation:
                return None
            
            # Создаем ставку через нейронную сеть
            bet = self.neural_trader.make_bet(market_data, strategy_signals)
            
            if bet:
                bet_id = f"neural_bet_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:20]}"
                bet['bet_id'] = bet_id
                bet['type'] = 'neural_bet'
                bet['recommendation'] = recommendation
                bet['market_conditions'] = recommendation.get('market_conditions', {})
                
                # Интеграция с риск-менеджером
                if self.risk_integration_enabled and self.risk_manager:
                    # Регистрируем нейронную ставку как виртуальную позицию
                    try:
                        virtual_signal = {
                            'signal': 'BUY',  # Нейронные ставки всегда "покупают" стратегию
                            'entry_price': bet['bet_amount'],
                            'stop_loss': bet['bet_amount'] * 0.5,  # 50% стоп-лосс
                            'take_profit': bet['bet_amount'] * 1.5,  # 50% прибыль
                            'strategy': f"neural_{bet['strategy']}",
                            'comment': f"Neural bet on {bet['strategy']}"
                        }
                        
                        # Фиктивный order_response для риск-менеджера
                        mock_response = {
                            'retCode': 0,
                            'result': {
                                'orderId': bet_id,
                                'qty': str(bet['bet_amount'])
                            }
                        }
                        
                        self.risk_manager.register_trade(
                            f"neural_{bet['strategy']}", virtual_signal, mock_response
                        )
                        
                    except Exception as e:
                        self.logger.error(f"Ошибка регистрации в риск-менеджере: {e}")
                
                # Сохраняем ставку
                self.active_bets[bet_id] = bet
                
                self.logger.info(f"Размещена нейронная ставка {bet_id} на {bet['strategy']} "
                               f"(сумма: ${bet['bet_amount']:.2f}, уверенность: {bet['confidence']:.3f})")
                
                return bet
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка размещения нейронной ставки: {e}")
            return None
    
    def update_bet_results(self, bet_id: str, result: Dict):
        """Обновление результатов ставки с расширенной аналитикой"""
        if bet_id not in self.active_bets:
            self.logger.warning(f"Ставка {bet_id} не найдена в активных ставках")
            return
        
        try:
            bet = self.active_bets.pop(bet_id)
            
            # Обновляем производительность нейронной сети
            self.neural_trader.update_performance(bet, result)
            
            # Анализируем результат для калибровки уверенности
            self._analyze_bet_result(bet, result)
            
            # Сохраняем завершенную сделку с расширенной информацией
            completed_trade = {
                'bet': bet,
                'result': result,
                'completion_time': datetime.now().isoformat(),
                'duration_hours': self._calculate_bet_duration(bet),
                'market_conditions_at_close': self._get_current_market_snapshot(),
                'analysis': {
                    'expected_outcome': bet['confidence'],
                    'actual_outcome': 1.0 if result.get('success') else 0.0,
                    'confidence_error': abs(bet['confidence'] - (1.0 if result.get('success') else 0.0)),
                    'strategy_match': bet['strategy'] == result.get('winning_strategy', '')
                }
            }
            
            self.completed_trades.append(completed_trade)
            
            # Ограничиваем историю сделок
            if len(self.completed_trades) > 1000:
                self.completed_trades = self.completed_trades[-1000:]
            
            # Обновляем риск-менеджер
            if self.risk_integration_enabled and self.risk_manager:
                try:
                    realized_pnl = result.get('profit', -bet['bet_amount'])
                    self.risk_manager.close_position(
                        f"neural_{bet['strategy']}", "NEURAL", bet['bet_amount'], realized_pnl
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка обновления риск-менеджера: {e}")
            
            success_msg = "успешна ✅" if result.get('success') else "неуспешна ❌"
            profit_msg = f"${result.get('profit', 0):.2f}"
            
            self.logger.info(f"Результат ставки {bet_id}: {success_msg}, "
                           f"прибыль: {profit_msg}, "
                           f"продолжительность: {completed_trade['duration_hours']:.1f}ч")
            
            # Запускаем автоматическое обучение если нужно
            self._trigger_auto_learning()
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления результатов ставки {bet_id}: {e}")
    
    def _analyze_bet_result(self, bet: Dict, result: Dict):
        """Анализ результата ставки для улучшения калибровки"""
        try:
            confidence = bet.get('confidence', 0.5)
            success = result.get('success', False)
            
            # Добавляем в историю калибровки уверенности
            self.confidence_calibration_history.append({
                'timestamp': datetime.now().isoformat(),
                'predicted_confidence': confidence,
                'actual_outcome': 1.0 if success else 0.0,
                'strategy': bet.get('strategy'),
                'bet_amount': bet.get('bet_amount', 0),
                'market_conditions': bet.get('market_conditions', {})
            })
            
            # Ограничиваем историю
            if len(self.confidence_calibration_history) > 500:
                self.confidence_calibration_history = self.confidence_calibration_history[-500:]
                
        except Exception as e:
            self.logger.error(f"Ошибка анализа результата ставки: {e}")
    
    def _calculate_bet_duration(self, bet: Dict) -> float:
        """Расчет продолжительности ставки в часах"""
        try:
            bet_time = datetime.fromisoformat(bet['timestamp'])
            current_time = datetime.now()
            duration = (current_time - bet_time).total_seconds() / 3600
            return duration
        except:
            return 0.0
    
    def _get_current_market_snapshot(self) -> Dict:
        """Получение текущего снимка рыночных условий"""
        # Здесь можно добавить логику получения актуальных рыночных данных
        return {
            'timestamp': datetime.now().isoformat(),
            'note': 'Market snapshot not implemented'
        }
    
    def _trigger_auto_learning(self):
        """Запуск автоматического обучения при необходимости"""
        try:
            if not self.auto_learning_enabled:
                return
            
            current_time = datetime.now()
            time_since_last = (current_time - self.last_performance_check).total_seconds() / 3600
            
            if (time_since_last >= self.learning_frequency_hours and 
                len(self.completed_trades) >= self.min_samples_for_learning):
                
                self.logger.info("Запуск автоматического обучения...")
                
                # Анализируем последние результаты
                recent_trades = self.completed_trades[-self.min_samples_for_learning:]
                success_rate = sum(1 for trade in recent_trades 
                                 if trade['result'].get('success', False)) / len(recent_trades)
                
                # Обучаем нейронную сеть если производительность снижается
                if success_rate < 0.5:
                    self.neural_trader.train_with_validation()
                    self.logger.info(f"Автоматическое обучение завершено. "
                                   f"Текущая производительность: {success_rate:.1%}")
                
                self.last_performance_check = current_time
                
        except Exception as e:
            self.logger.error(f"Ошибка автоматического обучения: {e}")
    
    def get_neural_statistics(self) -> Dict:
        """Получение расширенной статистики нейронной интеграции"""
        try:
            # Базовая статистика нейронной сети
            neural_stats = self.neural_trader.get_advanced_statistics()
            
            # Статистика интеграции
            integration_stats = {
                'active_bets': len(self.active_bets),
                'completed_trades': len(self.completed_trades),
                'total_neural_trades': len(self.completed_trades),
                'integration_uptime_hours': (datetime.now() - self.last_performance_check).total_seconds() / 3600
            }
            
            # Анализ стратегий
            strategy_analysis = self.analyze_strategy_results()
            
            # Калибровка уверенности
            calibration_stats = self._analyze_confidence_calibration()
            
            # Анализ последних результатов
            recent_performance = self._analyze_recent_performance()
            
            return {
                'neural_trader': neural_stats,
                'integration': integration_stats,
                'strategy_analysis': strategy_analysis,
                'confidence_calibration': calibration_stats,
                'recent_performance': recent_performance,
                'risk_integration': {
                    'enabled': self.risk_integration_enabled,
                    'max_exposure_pct': self.max_neural_exposure_pct,
                    'position_limit': self.neural_position_limit
                },
                'auto_learning': {
                    'enabled': self.auto_learning_enabled,
                    'frequency_hours': self.learning_frequency_hours,
                    'min_samples': self.min_samples_for_learning,
                    'last_check': self.last_performance_check.isoformat()
                }
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики: {e}")
            return {'error': str(e)}
    
    def _analyze_confidence_calibration(self) -> Dict:
        """Анализ калибровки уверенности"""
        try:
            if not self.confidence_calibration_history:
                return {'status': 'insufficient_data'}
            
            # Группируем по диапазонам уверенности
            confidence_bins = {
                'low': [],      # 0.5 - 0.6
                'medium': [],   # 0.6 - 0.7
                'high': [],     # 0.7 - 0.8
                'very_high': [] # 0.8+
            }
            
            for record in self.confidence_calibration_history:
                confidence = record['predicted_confidence']
                outcome = record['actual_outcome']
                
                if confidence < 0.6:
                    confidence_bins['low'].append(outcome)
                elif confidence < 0.7:
                    confidence_bins['medium'].append(outcome)
                elif confidence < 0.8:
                    confidence_bins['high'].append(outcome)
                else:
                    confidence_bins['very_high'].append(outcome)
            
            # Анализируем калибровку по каждому диапазону
            calibration_analysis = {}
            for bin_name, outcomes in confidence_bins.items():
                if outcomes:
                    actual_success_rate = np.mean(outcomes)
                    calibration_analysis[bin_name] = {
                        'count': len(outcomes),
                        'actual_success_rate': actual_success_rate,
                        'sample_size': len(outcomes)
                    }
                else:
                    calibration_analysis[bin_name] = {
                        'count': 0,
                        'actual_success_rate': 0.0,
                        'sample_size': 0
                    }
            
            # Общая оценка калибровки
            all_predictions = [r['predicted_confidence'] for r in self.confidence_calibration_history]
            all_outcomes = [r['actual_outcome'] for r in self.confidence_calibration_history]
            
            # Brier Score (чем ниже, тем лучше)
            brier_score = np.mean([(pred - outcome)**2 for pred, outcome in zip(all_predictions, all_outcomes)])
            
            return {
                'brier_score': brier_score,
                'calibration_by_confidence': calibration_analysis,
                'total_samples': len(self.confidence_calibration_history),
                'overall_accuracy': np.mean(all_outcomes)
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа калибровки: {e}")
            return {'error': str(e)}
    
    def _analyze_recent_performance(self) -> Dict:
        """Анализ последней производительности"""
        try:
            if not self.completed_trades:
                return {'status': 'no_data'}
            
            # Последние 50 сделок или все если меньше
            recent_count = min(50, len(self.completed_trades))
            recent_trades = self.completed_trades[-recent_count:]
            
            # Базовые метрики
            successes = sum(1 for trade in recent_trades if trade['result'].get('success', False))
            success_rate = successes / len(recent_trades)
            
            # Прибыльность
            total_profit = sum(trade['result'].get('profit', 0) for trade in recent_trades)
            avg_profit = total_profit / len(recent_trades)
            
            # Анализ по стратегиям
            strategy_performance = {}
            for trade in recent_trades:
                strategy = trade['bet'].get('strategy', 'unknown')
                if strategy not in strategy_performance:
                    strategy_performance[strategy] = {'wins': 0, 'total': 0, 'profit': 0}
                
                strategy_performance[strategy]['total'] += 1
                if trade['result'].get('success', False):
                    strategy_performance[strategy]['wins'] += 1
                strategy_performance[strategy]['profit'] += trade['result'].get('profit', 0)
            
            # Добавляем винрейт для каждой стратегии
            for strategy, stats in strategy_performance.items():
                stats['win_rate'] = stats['wins'] / stats['total'] if stats['total'] > 0 else 0
            
            # Анализ ошибок калибровки
            calibration_errors = []
            for trade in recent_trades:
                predicted = trade['bet'].get('confidence', 0.5)
                actual = 1.0 if trade['result'].get('success', False) else 0.0
                calibration_errors.append(abs(predicted - actual))
            
            avg_calibration_error = np.mean(calibration_errors) if calibration_errors else 0
            
            return {
                'sample_size': len(recent_trades),
                'success_rate': success_rate,
                'total_profit': total_profit,
                'avg_profit_per_trade': avg_profit,
                'avg_calibration_error': avg_calibration_error,
                'strategy_breakdown': strategy_performance,
                'best_strategy': max(strategy_performance.items(), 
                                   key=lambda x: x[1]['win_rate'])[0] if strategy_performance else None,
                'worst_strategy': min(strategy_performance.items(), 
                                    key=lambda x: x[1]['win_rate'])[0] if strategy_performance else None
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа производительности: {e}")
            return {'error': str(e)}
    
    def get_strategy_ranking(self) -> List[Dict]:
        """Улучшенное ранжирование стратегий"""
        try:
            strategy_results = self.analyze_strategy_results()
            
            ranking = []
            for strategy_name, results in strategy_results.items():
                performance = results.get('performance', {})
                risk_metrics = results.get('risk_metrics', {})
                signal_quality = results.get('signal_quality', {})
                
                # Комплексная оценка стратегии
                score_components = {
                    'success_rate': performance.get('success_rate', 0.5) * 0.3,
                    'profit_factor': min(performance.get('profit_factor', 1.0) / 2.0, 1.0) * 0.25,
                    'signal_quality': signal_quality.get('quality_score', 0.5) * 0.2,
                    'stability': risk_metrics.get('stability_score', 0.5) * 0.15,
                    'risk_adjustment': {'low': 0.1, 'medium': 0.05, 'high': 0.0}.get(
                        risk_metrics.get('risk_level', 'medium'), 0.05) * 0.1
                }
                
                overall_score = sum(score_components.values())
                
                ranking.append({
                    'strategy': strategy_name,
                    'overall_score': overall_score,
                    'score_components': score_components,
                    'total_signals': results.get('basic_stats', {}).get('total_signals', 0),
                    'success_rate': performance.get('success_rate', 0.5) * 100,
                    'avg_profit': performance.get('avg_profit', 0),
                    'profit_factor': performance.get('profit_factor', 1.0),
                    'risk_level': risk_metrics.get('risk_level', 'medium'),
                    'signal_quality': signal_quality.get('quality_score', 0.5),
                    'recent_activity': results.get('time_patterns', {}).get('recent_activity', 0)
                })
            
            # Сортируем по общей оценке
            ranking.sort(key=lambda x: x['overall_score'], reverse=True)
            
            return ranking
            
        except Exception as e:
            self.logger.error(f"Ошибка ранжирования стратегий: {e}")
            return []
    
    def cleanup_old_bets(self):
        """Улучшенная очистка старых ставок"""
        current_time = datetime.now()
        expired_bets = []
        
        for bet_id, bet in self.active_bets.items():
            try:
                bet_time = datetime.fromisoformat(bet['timestamp'])
                hours_elapsed = (current_time - bet_time).total_seconds() / 3600
                
                if hours_elapsed > self.timeout_hours:
                    expired_bets.append(bet_id)
            except Exception as e:
                self.logger.error(f"Ошибка обработки ставки {bet_id}: {e}")
                expired_bets.append(bet_id)  # Удаляем проблемные ставки
        
        for bet_id in expired_bets:
            try:
                bet = self.active_bets[bet_id]
                
                # Помечаем как неудачную сделку
                result = {
                    'success': False,
                    'profit': -bet['bet_amount'],
                    'reason': 'timeout',
                    'timeout_hours': self.timeout_hours
                }
                
                self.update_bet_results(bet_id, result)
                self.logger.info(f"Ставка {bet_id} помечена как просроченная "
                               f"(возраст: {self.timeout_hours}ч)")
                
            except Exception as e:
                self.logger.error(f"Ошибка очистки ставки {bet_id}: {e}")
                # Принудительно удаляем проблемную ставку
                if bet_id in self.active_bets:
                    del self.active_bets[bet_id]
    
    def save_state(self):
        """Улучшенное сохранение состояния"""
        try:
            state = {
                'version': '2.0',
                'timestamp': datetime.now().isoformat(),
                'active_bets': self.active_bets,
                'completed_trades': self.completed_trades[-200:],  # Последние 200 сделок
                'prediction_accuracy_history': self.prediction_accuracy_history[-100:],
                'confidence_calibration_history': self.confidence_calibration_history[-100:],
                'settings': {
                    'profit_threshold': self.profit_threshold,
                    'timeout_hours': self.timeout_hours,
                    'cache_ttl_minutes': self.cache_ttl_minutes,
                    'max_neural_exposure_pct': self.max_neural_exposure_pct,
                    'neural_position_limit': self.neural_position_limit,
                    'auto_learning_enabled': self.auto_learning_enabled,
                    'learning_frequency_hours': self.learning_frequency_hours
                },
                'statistics': {
                    'last_performance_check': self.last_performance_check.isoformat(),
                    'total_active_bets': len(self.active_bets),
                    'total_completed_trades': len(self.completed_trades)
                }
            }
            
            os.makedirs('data/ai', exist_ok=True)
            
            # Основной файл состояния
            with open('data/ai/neural_integration_state.json', 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            # Бэкап с временной меткой
            backup_filename = f"data/ai/neural_integration_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_filename, 'w') as f:
                json.dump(state, f, default=str)
            
            # Очищаем старые бэкапы
            self._cleanup_old_integration_backups()
            
            self.logger.debug("Состояние нейронной интеграции сохранено")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения состояния: {e}")
    
    def _cleanup_old_integration_backups(self):
        """Очистка старых бэкапов интеграции"""
        try:
            import glob
            backup_files = glob.glob('data/ai/neural_integration_backup_*.json')
            backup_files.sort()
            
            # Оставляем только последние 3 бэкапа
            for old_backup in backup_files[:-3]:
                try:
                    os.remove(old_backup)
                except:
                    pass
        except:
            pass
    
    def load_state(self):
        """Улучшенная загрузка состояния"""
        try:
            state_path = 'data/ai/neural_integration_state.json'
            if not os.path.exists(state_path):
                self.logger.info("Файл состояния не найден, используем начальные настройки")
                return
            
            with open(state_path, 'r') as f:
                state = json.load(f)
            
            # Проверяем версию
            version = state.get('version', '1.0')
            if version != '2.0':
                self.logger.warning(f"Загружается состояние версии {version}, ожидалась 2.0")
            
            # Загружаем данные
            self.active_bets = state.get('active_bets', {})
            self.completed_trades = state.get('completed_trades', [])
            self.prediction_accuracy_history = state.get('prediction_accuracy_history', [])
            self.confidence_calibration_history = state.get('confidence_calibration_history', [])
            
            # Загружаем настройки
            settings = state.get('settings', {})
            self.profit_threshold = settings.get('profit_threshold', self.profit_threshold)
            self.timeout_hours = settings.get('timeout_hours', self.timeout_hours)
            self.cache_ttl_minutes = settings.get('cache_ttl_minutes', self.cache_ttl_minutes)
            self.max_neural_exposure_pct = settings.get('max_neural_exposure_pct', self.max_neural_exposure_pct)
            self.neural_position_limit = settings.get('neural_position_limit', self.neural_position_limit)
            self.auto_learning_enabled = settings.get('auto_learning_enabled', self.auto_learning_enabled)
            self.learning_frequency_hours = settings.get('learning_frequency_hours', self.learning_frequency_hours)
            
            # Загружаем статистику
            statistics = state.get('statistics', {})
            if 'last_performance_check' in statistics:
                try:
                    self.last_performance_check = datetime.fromisoformat(statistics['last_performance_check'])
                except:
                    self.last_performance_check = datetime.now()
            
            self.logger.info(f"Состояние загружено: {len(self.active_bets)} активных ставок, "
                           f"{len(self.completed_trades)} завершенных сделок")
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки состояния: {e}")
            self.logger.info("Используем настройки по умолчанию")
    
    def reset_integration(self):
        """Сброс интеграции к начальному состоянию"""
        self.logger.info("Сброс нейронной интеграции к начальному состоянию")
        
        # Очищаем все данные
        self.active_bets = {}
        self.completed_trades = []
        self.strategy_performance_cache = {}
        self.prediction_accuracy_history = []
        self.confidence_calibration_history = []
        
        # Сбрасываем временные метки
        self.last_performance_check = datetime.now()
        
        # Сбрасываем нейронную сеть
        self.neural_trader.reset_model()
        
        # Сохраняем сброшенное состояние
        self.save_state()
        
        self.logger.info("Нейронная интеграция успешно сброшена")