# bot/ai/neural_trader.py
# Нейронная сеть для анализа торговых стратегий и принятия решений
# Функции: предсказание производительности, обучение с подкреплением, управление ставками

import numpy as np
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging

class NeuralTrader:
    """
    Улучшенная нейронная сеть для торгового анализа
    
    Архитектура:
    - Входной слой: рыночные данные + сигналы стратегий (с валидацией)
    - Скрытые слои: анализ паттернов с регуляризацией
    - Выходной слой: вероятность успеха стратегий
    - Система обучения: reinforcement learning + регуляризация
    """
    
    def __init__(self, 
                 input_size: int = 152,  # ОПТИМИЗИРОВАНО: увеличен для полного охвата features
                 hidden_size: int = 64,   # ОПТИМИЗИРОВАНО: пропорционально увеличен
                 output_size: int = 10,
                 learning_rate: float = 0.001,
                 memory_size: int = 1000,
                 l2_lambda: float = 0.001,
                 dropout_rate: float = 0.15): # ОПТИМИЗИРОВАНО: снижен для большей сети
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.learning_rate = learning_rate
        self.memory_size = memory_size
        self.l2_lambda = l2_lambda
        self.dropout_rate = dropout_rate
        
        # Инициализация весов (Xavier/Glorot)
        self.weights1 = np.random.randn(input_size, hidden_size) * np.sqrt(2.0 / input_size)
        self.weights2 = np.random.randn(hidden_size, hidden_size) * np.sqrt(2.0 / hidden_size)
        self.weights3 = np.random.randn(hidden_size, output_size) * np.sqrt(2.0 / hidden_size)
        
        # Смещения
        self.bias1 = np.zeros((1, hidden_size))
        self.bias2 = np.zeros((1, hidden_size))
        self.bias3 = np.zeros((1, output_size))
        
        # Адаптивный learning rate
        self.initial_lr = learning_rate
        self.lr_decay = 0.95
        self.min_lr = 0.0001
        
        # Batch normalization параметры
        self.running_mean1 = np.zeros((1, hidden_size))
        self.running_var1 = np.ones((1, hidden_size))
        self.running_mean2 = np.zeros((1, hidden_size))
        self.running_var2 = np.ones((1, hidden_size))
        self.bn_momentum = 0.9
        
        # Early stopping
        self.best_loss = float('inf')
        self.patience = 10
        self.no_improve_count = 0
        
        # Память для обучения
        self.memory = []
        self.performance_history = []
        
        # Логирование
        self.logger = logging.getLogger('neural_trader')
        
        # Статистика
        self.total_bets = 0
        self.winning_bets = 0
        self.current_balance = 1000.0
        self.bet_amount = 10.0
        self.max_bet_amount = 50.0  # Максимальная ставка
        self.min_bet_amount = 5.0   # Минимальная ставка
        
        # Метрики качества
        self.prediction_accuracy = 0.0
        self.confidence_threshold = 0.6
        self.min_confidence = 0.5
        self.max_confidence = 0.95
        
        # Загружаем сохраненную модель
        self.load_model()
    
    def relu(self, x: np.ndarray) -> np.ndarray:
        """Функция активации ReLU с клиппингом"""
        return np.clip(np.maximum(0, x), 0, 10)  # Предотвращаем взрыв градиентов
    
    def relu_derivative(self, x: np.ndarray) -> np.ndarray:
        """Производная ReLU"""
        return np.where((x > 0) & (x < 10), 1, 0)
    
    def leaky_relu(self, x: np.ndarray, alpha: float = 0.01) -> np.ndarray:
        """Leaky ReLU для лучшего обучения"""
        return np.where(x > 0, x, alpha * x)
    
    def leaky_relu_derivative(self, x: np.ndarray, alpha: float = 0.01) -> np.ndarray:
        """Производная Leaky ReLU"""
        return np.where(x > 0, 1, alpha)
    
    def softmax(self, x: np.ndarray) -> np.ndarray:
        """Улучшенная функция Softmax с численной стабильностью"""
        # Предотвращаем переполнение
        x_shifted = x - np.max(x, axis=1, keepdims=True)
        exp_x = np.exp(np.clip(x_shifted, -500, 500))
        return exp_x / (np.sum(exp_x, axis=1, keepdims=True) + 1e-8)
    
    def batch_normalize(self, x: np.ndarray, running_mean: np.ndarray, 
                       running_var: np.ndarray, training: bool = True) -> np.ndarray:
        """Batch normalization для стабильного обучения"""
        if training:
            batch_mean = np.mean(x, axis=0, keepdims=True)
            batch_var = np.var(x, axis=0, keepdims=True)
            
            # Обновляем running statistics
            running_mean[:] = (self.bn_momentum * running_mean + 
                             (1 - self.bn_momentum) * batch_mean)
            running_var[:] = (self.bn_momentum * running_var + 
                            (1 - self.bn_momentum) * batch_var)
            
            # Нормализация
            x_norm = (x - batch_mean) / np.sqrt(batch_var + 1e-8)
        else:
            x_norm = (x - running_mean) / np.sqrt(running_var + 1e-8)
        
        return x_norm
    
    def dropout(self, x: np.ndarray, training: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """Dropout для предотвращения переобучения"""
        if training and self.dropout_rate > 0:
            mask = np.random.binomial(1, 1 - self.dropout_rate, x.shape) / (1 - self.dropout_rate)
            return x * mask, mask
        return x, np.ones_like(x)
    
    def prepare_input_safe(self, market_data: Dict, strategy_signals: Dict) -> np.ndarray:
        """Безопасная подготовка входных данных с расширенной валидацией"""
        features = []
        
        try:
            # Рыночные данные с улучшенной обработкой
            timeframes = ['1m', '5m', '15m', '1h']
            for tf in timeframes:
                if tf in market_data and market_data[tf] is not None:
                    # Преобразуем данные в DataFrame если нужно
                    tf_data = market_data[tf]
                    if isinstance(tf_data, dict):
                        # Конвертируем dict в DataFrame
                        try:
                            tf_data = pd.DataFrame(tf_data)
                        except Exception as e:
                            self.logger.warning(f"Не удалось конвертировать данные {tf} в DataFrame: {e}")
                            features.extend([0] * 8)
                            continue

                    if isinstance(tf_data, pd.DataFrame) and not tf_data.empty:
                        df = tf_data.tail(20).copy()  # Увеличиваем окно

                        # Конвертируем в числовой формат
                        for col in ['open', 'high', 'low', 'close', 'volume']:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')

                        # Убираем NaN
                        df = df.dropna()

                        if len(df) > 5:  # Минимум 5 свечей для расчета
                            # Расширенные технические индикаторы
                            close_prices = df['close'].values
                            volumes = df['volume'].values if 'volume' in df.columns else np.ones(len(df))

                            # Ценовые характеристики
                            price_change = self._safe_divide(close_prices[-1] - close_prices[0], close_prices[0])
                            high_values = df['high'].values if 'high' in df.columns else close_prices
                            low_values = df['low'].values if 'low' in df.columns else close_prices
                            volatility = self._safe_divide(high_values.max() - low_values.min(), close_prices[-1])

                            # Объемные характеристики
                            volume_trend = self._safe_divide(volumes[-1], np.mean(volumes[:-1])) if len(volumes) > 1 else 1
                            volume_std = np.std(volumes) / (np.mean(volumes) + 1e-8)

                            # Трендовые характеристики
                            sma_5 = np.mean(close_prices[-5:])
                            sma_10 = np.mean(close_prices[-10:]) if len(close_prices) >= 10 else sma_5
                            trend_strength = self._safe_divide(sma_5 - sma_10, sma_10)

                            # Волатильность и моментум
                            returns = np.diff(close_prices) / close_prices[:-1]
                            volatility_std = np.std(returns) if len(returns) > 0 else 0
                            momentum = self._safe_divide(close_prices[-1] - close_prices[-3], close_prices[-3]) if len(close_prices) >= 3 else 0

                            # Нормализация и клиппинг
                            features.extend([
                                np.clip(price_change, -0.2, 0.2),      # ±20%
                                np.clip(volatility, 0, 0.3),           # До 30%
                                np.clip(volume_trend, 0.1, 5.0),       # 0.1x - 5x
                                np.clip(volume_std, 0, 2.0),           # До 200%
                                np.clip(trend_strength, -0.1, 0.1),    # ±10%
                                np.clip(volatility_std, 0, 0.1),       # До 10%
                                np.clip(momentum, -0.1, 0.1),          # ±10%
                                1 if close_prices[-1] > close_prices[0] else 0  # Направление
                            ])
                        else:
                            features.extend([0] * 8)
                    else:
                        features.extend([0] * 8)
                else:
                    features.extend([0] * 8)
            
            # 📈 РАСШИРЕННЫЕ сигналы стратегий (увеличено с 4 до 8 features)
            strategy_names = [f'strategy_{i:02d}' for i in range(1, 11)]
            for strategy_name in strategy_names:
                if strategy_name in strategy_signals:
                    signal = strategy_signals[strategy_name]
                    if signal and isinstance(signal, dict):
                        # Кодируем тип сигнала
                        signal_type = signal.get('signal', '')
                        if signal_type == 'BUY':
                            signal_value = 1.0
                        elif signal_type == 'SELL':
                            signal_value = -1.0
                        else:
                            signal_value = 0.0
                        
                        # Анализ цены входа
                        entry_price = float(signal.get('entry_price', 0))
                        current_price = self._get_current_price(market_data)
                        
                        price_deviation = 0
                        if current_price > 0 and entry_price > 0:
                            price_deviation = self._safe_divide(entry_price - current_price, current_price)
                            price_deviation = np.clip(price_deviation, -0.1, 0.1)  # ±10%
                        
                        # Качество сигнала
                        signal_strength = float(signal.get('signal_strength', 0.5))
                        signal_strength = np.clip(signal_strength, 0, 1)
                        
                        # Risk/Reward ratio
                        rr_ratio = float(signal.get('risk_reward_ratio', 1.0))
                        rr_ratio = np.clip(rr_ratio, 0.5, 5.0)  # От 0.5 до 5.0
                        rr_ratio_norm = (rr_ratio - 1.0) / 4.0  # Нормализуем к [-0.125, 1.0]
                        
                        # 📈 РАСШИРЕННЫЕ features стратегии (4 → 8)
                        stop_loss = float(signal.get('stop_loss', entry_price * 0.95))
                        take_profit = float(signal.get('take_profit', entry_price * 1.05))
                        time_decay = float(signal.get('time_in_position', 0)) / 3600  # часы
                        confidence_decay = signal_strength * np.exp(-time_decay * 0.1)  # экспоненциальное затухание
                        
                        features.extend([
                            signal_value, price_deviation, signal_strength, rr_ratio_norm,
                            np.clip(time_decay, 0, 24),  # макс 24 часа
                            np.clip(confidence_decay, 0, 1),  # затухающая уверенность
                            1 if signal_type == 'BUY' else (0.5 if signal_type == 'SELL' else 0),  # категориальный сигнал  
                            np.clip(abs(price_deviation), 0, 0.1)  # абсолютное отклонение
                        ])
                    else:
                        features.extend([0, 0, 0.5, 0, 0, 0.5, 0, 0])  # 8 нейтральных features
                else:
                    features.extend([0, 0, 0.5, 0, 0, 0.5, 0, 0])  # 8 нейтральных features
            
            # 🔭 РАСШИРЕННЫЕ рыночные индикаторы (2 → 16)
            market_sentiment = self._calculate_market_sentiment(market_data)
            volatility_index = self._calculate_volatility_index(market_data)
            trend_strength = self._calculate_trend_strength(market_data)
            momentum_divergence = self._calculate_momentum_divergence(market_data)
            volume_profile = self._calculate_volume_profile(market_data)
            correlation_matrix = self._calculate_timeframe_correlation(market_data)
            
            # Микроструктурные характеристики
            spread_dynamics = self._calculate_spread_dynamics(market_data)
            order_flow_imbalance = self._calculate_order_flow_imbalance(market_data)
            
            # Временные факторы
            time_features = self._extract_temporal_features()
            
            features.extend([
                # Основные рыночные индикаторы (6)
                np.clip(market_sentiment, -1, 1),
                np.clip(volatility_index, 0, 2),
                np.clip(trend_strength, -1, 1),
                np.clip(momentum_divergence, -1, 1),
                np.clip(volume_profile, 0, 2),
                np.clip(correlation_matrix, -1, 1),
                
                # Микроструктура (2)
                np.clip(spread_dynamics, 0, 1),
                np.clip(order_flow_imbalance, -1, 1),
                
                # Временные факторы (8)
                *time_features
            ])
            
            # 🚨 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: без потерь информации!
            # Теперь сохраняем ВСЕ features без обрезки
            if len(features) < self.input_size:
                # Дополняем нулями только если недостает данных
                padding_needed = self.input_size - len(features)
                features.extend([0.0] * padding_needed)
                self.logger.debug(f"Дополнено {padding_needed} нулевых features")
            elif len(features) > self.input_size:
                # ЛОГИРУЕМ ПРОБЛЕМУ - не обрезаем!
                excess_features = len(features) - self.input_size
                self.logger.warning(f"ПОТЕРЯ ИНФОРМАЦИИ! {excess_features} features обрезаны")
                features = features[:self.input_size]
            
            # Финальная проверка на NaN и Inf
            features = [0.0 if (np.isnan(f) or np.isinf(f)) else float(f) for f in features]
            
            return np.array(features, dtype=np.float32).reshape(1, -1)
            
        except Exception as e:
            self.logger.error(f"Ошибка подготовки входных данных: {e}")
            # Возвращаем нулевой вектор с новым размером
            return np.zeros((1, self.input_size), dtype=np.float32)
    
    def _safe_divide(self, a, b, default=0.0):
        """Безопасное деление с обработкой деления на ноль"""
        try:
            if b == 0 or np.isnan(b) or np.isinf(b):
                return default
            result = a / b
            return result if not (np.isnan(result) or np.isinf(result)) else default
        except:
            return default
    
    def _get_current_price(self, market_data: Dict) -> float:
        """Получение текущей цены из рыночных данных"""
        try:
            for tf in ['1m', '5m', '15m', '1h']:
                if (tf in market_data and market_data[tf] is not None and 
                    not market_data[tf].empty):
                    return float(market_data[tf].iloc[-1]['close'])
        except:
            pass
        return 0.0
    
    def _calculate_market_sentiment(self, market_data: Dict) -> float:
        """Расчет настроения рынка на основе нескольких таймфреймов"""
        try:
            sentiment_scores = []
            
            for tf in ['5m', '15m', '1h']:
                if (tf in market_data and market_data[tf] is not None and 
                    not market_data[tf].empty):
                    df = market_data[tf].tail(10)
                    if len(df) > 1:
                        # Простой индикатор настроения: соотношение роста к падению
                        price_changes = df['close'].pct_change().dropna()
                        if len(price_changes) > 0:
                            positive_changes = (price_changes > 0).sum()
                            total_changes = len(price_changes)
                            sentiment = (positive_changes / total_changes - 0.5) * 2  # От -1 до 1
                            sentiment_scores.append(sentiment)
            
            return np.mean(sentiment_scores) if sentiment_scores else 0.0
        except:
            return 0.0
    
    def _calculate_volatility_index(self, market_data: Dict) -> float:
        """Расчет индекса волатильности"""
        try:
            volatilities = []
            
            for tf in ['5m', '15m', '1h']:
                if (tf in market_data and market_data[tf] is not None and 
                    not market_data[tf].empty):
                    df = market_data[tf].tail(20)
                    if len(df) > 1:
                        returns = df['close'].pct_change().dropna()
                        if len(returns) > 0:
                            volatility = returns.std()
                            volatilities.append(volatility)
            
            return np.mean(volatilities) * 100 if volatilities else 0.0  # В процентах
        except:
            return 0.0
    
    def forward_improved(self, x: np.ndarray, training: bool = True) -> Tuple[np.ndarray, Dict]:
        """Улучшенный прямой проход с нормализацией и dropout"""
        activations = {'input': x}
        
        try:
            # Первый слой
            z1 = np.dot(x, self.weights1) + self.bias1
            z1_norm = self.batch_normalize(z1, self.running_mean1, self.running_var1, training)
            a1 = self.leaky_relu(z1_norm)
            a1_drop, dropout_mask1 = self.dropout(a1, training)
            activations.update({'z1': z1, 'z1_norm': z1_norm, 'a1': a1, 'a1_drop': a1_drop, 'mask1': dropout_mask1})
            
            # Второй слой
            z2 = np.dot(a1_drop, self.weights2) + self.bias2
            z2_norm = self.batch_normalize(z2, self.running_mean2, self.running_var2, training)
            a2 = self.leaky_relu(z2_norm)
            a2_drop, dropout_mask2 = self.dropout(a2, training)
            activations.update({'z2': z2, 'z2_norm': z2_norm, 'a2': a2, 'a2_drop': a2_drop, 'mask2': dropout_mask2})
            
            # Выходной слой
            z3 = np.dot(a2_drop, self.weights3) + self.bias3
            a3 = self.softmax(z3)
            activations.update({'z3': z3, 'a3': a3})
            
            return a3, activations
            
        except Exception as e:
            self.logger.error(f"Ошибка в прямом проходе: {e}")
            # Возвращаем равномерное распределение в случае ошибки
            uniform_output = np.ones((1, self.output_size)) / self.output_size
            return uniform_output, {'input': x}

    def predict(self, x: np.ndarray) -> np.ndarray:
        """
        Публичный метод для предсказания (обертка над forward_improved)

        Args:
            x: Входные данные shape (batch_size, input_size)

        Returns:
            Предсказания shape (batch_size, output_size)
        """
        try:
            # Валидация входных данных
            if x is None:
                raise ValueError("Входные данные не могут быть None")

            if not isinstance(x, np.ndarray):
                x = np.array(x, dtype=np.float32)

            # Проверяем размерность
            if len(x.shape) == 1:
                x = x.reshape(1, -1)

            if x.shape[1] != self.input_size:
                self.logger.warning(f"Неожиданный размер входных данных: {x.shape[1]}, ожидался: {self.input_size}")
                # Обрезаем или дополняем нулями
                if x.shape[1] > self.input_size:
                    x = x[:, :self.input_size]
                else:
                    x = np.pad(x, ((0, 0), (0, self.input_size - x.shape[1])), mode='constant')

            # Делаем предсказание (inference mode)
            prediction, _ = self.forward_improved(x, training=False)

            return prediction

        except Exception as e:
            self.logger.error(f"Ошибка предсказания: {e}")
            # Возвращаем равномерное распределение
            return np.ones((1, self.output_size)) / self.output_size

    def predict_strategy_performance(self, market_data: Dict, strategy_signals: Dict) -> Dict[str, float]:
        """Предсказание производительности стратегий с улучшенной обработкой"""
        try:
            x = self.prepare_input_safe(market_data, strategy_signals)
            predictions, _ = self.forward_improved(x, training=False)
            
            strategy_names = [f'strategy_{i:02d}' for i in range(1, 11)]
            results = {}
            
            for i, strategy_name in enumerate(strategy_names):
                if i < len(predictions[0]):
                    # Применяем температурное масштабирование для калибровки уверенности
                    confidence = float(predictions[0][i])
                    # Ограничиваем уверенность разумными пределами
                    confidence = np.clip(confidence, self.min_confidence, self.max_confidence)
                    results[strategy_name] = confidence
                else:
                    results[strategy_name] = 0.5  # Нейтральная уверенность
            
            return results
            
        except Exception as e:
            self.logger.error(f"Ошибка предсказания: {e}")
            # Возвращаем нейтральные предсказания
            strategy_names = [f'strategy_{i:02d}' for i in range(1, 11)]
            return {name: 0.5 for name in strategy_names}
    
    def make_bet(self, market_data: Dict, strategy_signals: Dict) -> Optional[Dict]:
        """Принятие решения о ставке с динамическим управлением размером"""
        try:
            predictions = self.predict_strategy_performance(market_data, strategy_signals)
            
            if not predictions:
                return None
            
            # Находим лучшую стратегию
            best_strategy = max(predictions.items(), key=lambda x: x[1])
            strategy_name, confidence = best_strategy
            
            # Динамический порог на основе текущей производительности
            dynamic_threshold = self._calculate_dynamic_threshold()
            
            if confidence > dynamic_threshold:
                # Динамический размер ставки на основе уверенности
                bet_size = self._calculate_bet_size(confidence)
                
                bet = {
                    'strategy': strategy_name,
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat(),
                    'bet_amount': bet_size,
                    'threshold_used': dynamic_threshold,
                    'all_predictions': predictions,
                    'market_data': self._serialize_market_data(market_data)
                }
                
                self.total_bets += 1
                self.logger.info(f"Нейронная ставка: {strategy_name} "
                               f"(уверенность: {confidence:.3f}, размер: ${bet_size:.2f})")
                
                return bet
            else:
                self.logger.debug(f"Уверенность {confidence:.3f} ниже порога {dynamic_threshold:.3f}")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка принятия решения о ставке: {e}")
            return None
    
    def _calculate_dynamic_threshold(self) -> float:
        """Расчет динамического порога уверенности"""
        try:
            if self.total_bets == 0:
                return self.confidence_threshold
            
            win_rate = self.winning_bets / self.total_bets
            
            # Адаптивный порог: если винрейт высокий - снижаем порог, если низкий - повышаем
            if win_rate > 0.6:
                # Хорошая производительность - можем быть менее консервативными
                threshold = max(0.55, self.confidence_threshold - 0.1)
            elif win_rate < 0.4:
                # Плохая производительность - становимся более консервативными
                threshold = min(0.8, self.confidence_threshold + 0.1)
            else:
                threshold = self.confidence_threshold
            
            return threshold
            
        except:
            return self.confidence_threshold
    
    def _calculate_bet_size(self, confidence: float) -> float:
        """Расчет размера ставки на основе уверенности и текущего баланса"""
        try:
            # Kelly Criterion inspired sizing
            base_fraction = 0.02  # 2% от баланса как база
            confidence_multiplier = (confidence - 0.5) * 2  # От 0 до 1
            
            # Учитываем текущую производительность
            if self.total_bets > 10:
                win_rate = self.winning_bets / self.total_bets
                performance_multiplier = min(2.0, max(0.5, win_rate * 2))
            else:
                performance_multiplier = 1.0
            
            # Размер ставки как процент от баланса
            fraction = base_fraction * confidence_multiplier * performance_multiplier
            bet_size = self.current_balance * fraction
            
            # Ограничиваем размер ставки
            bet_size = np.clip(bet_size, self.min_bet_amount, self.max_bet_amount)
            
            return round(bet_size, 2)
            
        except:
            return self.bet_amount
    
    def _serialize_market_data(self, market_data: Dict) -> Dict:
        """Сериализация рыночных данных для сохранения"""
        try:
            serialized = {}
            for tf, df in market_data.items():
                if df is not None and not df.empty:
                    # Берем только последнюю свечу для экономии места
                    last_candle = df.iloc[-1].to_dict()
                    serialized[tf] = last_candle
                else:
                    serialized[tf] = {}
            return serialized
        except:
            return {}
    
    def update_performance(self, bet: Dict, result: Dict):
        """Обновление производительности с расширенной аналитикой"""
        if not bet:
            return
        
        try:
            strategy_name = bet['strategy']
            success = result.get('success', False)
            profit = result.get('profit', 0)
            
            # Обновляем статистику
            if success:
                self.winning_bets += 1
                self.current_balance += profit
                reward = 1.0
            else:
                self.current_balance = max(0, self.current_balance - bet['bet_amount'])
                reward = -1.0
            
            # Добавляем в историю производительности
            performance_record = {
                'timestamp': datetime.now().isoformat(),
                'strategy': strategy_name,
                'confidence': bet['confidence'],
                'bet_amount': bet['bet_amount'],
                'success': success,
                'profit': profit,
                'balance': self.current_balance,
                'win_rate': self.winning_bets / self.total_bets if self.total_bets > 0 else 0
            }
            self.performance_history.append(performance_record)
            
            # Ограничиваем историю
            if len(self.performance_history) > 1000:
                self.performance_history = self.performance_history[-1000:]
            
            # Сохраняем опыт для обучения
            experience = {
                'bet': bet,
                'result': result,
                'reward': reward,
                'timestamp': datetime.now().isoformat()
            }
            
            self.memory.append(experience)
            if len(self.memory) > self.memory_size:
                self.memory.pop(0)
            
            # Обучаем нейронную сеть
            if len(self.memory) >= 10:
                self.train_with_validation()
            
            # Сохраняем модель
            self.save_model()
            
            # Логируем результат
            win_rate = (self.winning_bets / self.total_bets * 100) if self.total_bets > 0 else 0
            roi = ((self.current_balance - 1000.0) / 1000.0 * 100)
            
            self.logger.info(f"Ставка {'✅ успешна' if success else '❌ неуспешна'}. "
                           f"Баланс: ${self.current_balance:.2f}, "
                           f"Винрейт: {win_rate:.1f}%, ROI: {roi:.1f}%")
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления производительности: {e}")
    
    def train_with_validation(self, train_ratio: float = 0.8):
        """Обучение с валидационной выборкой и early stopping"""
        try:
            if len(self.memory) < 20:
                return
            
            # Разделяем данные
            experiences = self.memory.copy()
            np.random.shuffle(experiences)
            
            split_idx = int(len(experiences) * train_ratio)
            train_exp = experiences[:split_idx]
            val_exp = experiences[split_idx:]
            
            # Обучаем на train данных
            train_loss = self._train_batch(train_exp, training=True)
            
            # Валидируем на validation данных
            val_loss = self._train_batch(val_exp, training=False)
            
            # Early stopping и адаптивный learning rate
            if val_loss < self.best_loss:
                self.best_loss = val_loss
                self.no_improve_count = 0
            else:
                self.no_improve_count += 1
                if self.no_improve_count >= self.patience:
                    # Снижаем learning rate
                    self.learning_rate = max(self.learning_rate * self.lr_decay, self.min_lr)
                    self.no_improve_count = 0
                    self.logger.info(f"Learning rate снижен до {self.learning_rate:.6f}")
            
            self.logger.debug(f"Train loss: {train_loss:.4f}, Val loss: {val_loss:.4f}")
            
        except Exception as e:
            self.logger.error(f"Ошибка обучения: {e}")
    
    def _train_batch(self, experiences: List, training: bool = True) -> float:
        """Обучение на батче данных"""
        if not experiences:
            return 0.0
        
        total_loss = 0
        successful_updates = 0
        
        for experience in experiences:
            try:
                bet = experience['bet']
                reward = experience['reward']
                
                # Восстанавливаем рыночные данные
                market_data_df = self._deserialize_market_data(bet.get('market_data', {}))
                strategy_signals = {bet['strategy']: {'signal': 'BUY'}}
                
                x = self.prepare_input_safe(market_data_df, strategy_signals)
                predictions, activations = self.forward_improved(x, training=training)
                
                # Создаем целевые значения с soft targets
                target = np.full((1, self.output_size), 0.1)  # Базовое значение
                strategy_names = [f'strategy_{i:02d}' for i in range(1, 11)]
                
                if bet['strategy'] in strategy_names:
                    strategy_index = strategy_names.index(bet['strategy'])
                    if strategy_index < self.output_size:
                        if reward > 0:
                            target[0, strategy_index] = 0.9  # Успешная стратегия
                        else:
                            target[0, strategy_index] = 0.1  # Неуспешная стратегия
                
                # Вычисляем loss с регуляризацией
                loss = self._calculate_loss_with_regularization(predictions, target)
                total_loss += loss
                
                # Обратное распространение только для training
                if training:
                    self._backpropagate_improved(x, target, activations)
                
                successful_updates += 1
                
            except Exception as e:
                self.logger.error(f"Ошибка обучения на опыте: {e}")
                continue
        
        return total_loss / successful_updates if successful_updates > 0 else 0.0
    
    def _deserialize_market_data(self, serialized_data: Dict) -> Dict:
        """Восстановление рыночных данных из сериализованного формата"""
        try:
            market_data_df = {}
            for tf, data in serialized_data.items():
                if data and isinstance(data, dict):
                    market_data_df[tf] = pd.DataFrame([data])
                else:
                    market_data_df[tf] = pd.DataFrame()
            return market_data_df
        except:
            return {}
    
    def _calculate_loss_with_regularization(self, predictions: np.ndarray, targets: np.ndarray) -> float:
        """Функция потерь с L2 регуляризацией"""
        try:
            # Cross-entropy loss
            ce_loss = -np.mean(targets * np.log(predictions + 1e-8))
            
            # L2 регуляризация
            l2_loss = (self.l2_lambda * (np.sum(self.weights1**2) + 
                                        np.sum(self.weights2**2) + 
                                        np.sum(self.weights3**2)))
            
            return ce_loss + l2_loss
        except:
            return 1.0
    
    def _backpropagate_improved(self, x: np.ndarray, target: np.ndarray, activations: Dict):
        """Улучшенное обратное распространение с градиентным клиппингом"""
        try:
            a3 = activations.get('a3')
            a2_drop = activations.get('a2_drop')
            a1_drop = activations.get('a1_drop')
            z2_norm = activations.get('z2_norm')
            z1_norm = activations.get('z1_norm')
            
            if any(v is None for v in [a3, a2_drop, a1_drop, z2_norm, z1_norm]):
                return
            
            # Ошибка на выходном слое
            error3 = a3 - target
            delta3 = error3
            
            # Ошибка на втором слое
            error2 = np.dot(delta3, self.weights3.T)
            delta2 = error2 * self.leaky_relu_derivative(z2_norm)
            
            # Ошибка на первом слое
            error1 = np.dot(delta2, self.weights2.T)
            delta1 = error1 * self.leaky_relu_derivative(z1_norm)
            
            # Градиентное клиппинг
            delta3 = np.clip(delta3, -1, 1)
            delta2 = np.clip(delta2, -1, 1)
            delta1 = np.clip(delta1, -1, 1)
            
            # Обновление весов с L2 регуляризацией
            self.weights3 -= self.learning_rate * (np.dot(a2_drop.T, delta3) + 
                                                  self.l2_lambda * self.weights3)
            self.bias3 -= self.learning_rate * np.sum(delta3, axis=0, keepdims=True)
            
            self.weights2 -= self.learning_rate * (np.dot(a1_drop.T, delta2) + 
                                                  self.l2_lambda * self.weights2)
            self.bias2 -= self.learning_rate * np.sum(delta2, axis=0, keepdims=True)
            
            self.weights1 -= self.learning_rate * (np.dot(x.T, delta1) + 
                                                  self.l2_lambda * self.weights1)
            self.bias1 -= self.learning_rate * np.sum(delta1, axis=0, keepdims=True)
            
        except Exception as e:
            self.logger.error(f"Ошибка в обратном распространении: {e}")
    
    def get_advanced_statistics(self) -> Dict:
        """Расширенная статистика производительности"""
        try:
            base_stats = self.get_statistics()
            
            # Анализ последних результатов
            recent_performance = self.performance_history[-50:] if len(self.performance_history) >= 50 else self.performance_history
            
            if recent_performance:
                recent_win_rate = sum(1 for p in recent_performance if p['success']) / len(recent_performance)
                recent_avg_profit = np.mean([p['profit'] for p in recent_performance])
                recent_avg_confidence = np.mean([p['confidence'] for p in recent_performance])
                
                # Анализ по стратегиям
                strategy_performance = {}
                for perf in recent_performance:
                    strategy = perf['strategy']
                    if strategy not in strategy_performance:
                        strategy_performance[strategy] = {'wins': 0, 'total': 0, 'profits': []}
                    
                    strategy_performance[strategy]['total'] += 1
                    if perf['success']:
                        strategy_performance[strategy]['wins'] += 1
                    strategy_performance[strategy]['profits'].append(perf['profit'])
                
                # Расчет показателей по стратегиям
                for strategy, data in strategy_performance.items():
                    data['win_rate'] = data['wins'] / data['total'] if data['total'] > 0 else 0
                    data['avg_profit'] = np.mean(data['profits']) if data['profits'] else 0
                    data['total_profit'] = sum(data['profits'])
            else:
                recent_win_rate = 0
                recent_avg_profit = 0
                recent_avg_confidence = 0.5
                strategy_performance = {}
            
            # Расчет максимальной просадки
            balance_history = [p['balance'] for p in self.performance_history]
            max_drawdown = self._calculate_max_drawdown(balance_history)
            
            # Показатели качества модели
            prediction_accuracy = self._calculate_prediction_accuracy()
            
            advanced_stats = {
                **base_stats,
                'recent_performance': {
                    'win_rate': recent_win_rate * 100,
                    'avg_profit': recent_avg_profit,
                    'avg_confidence': recent_avg_confidence,
                    'samples': len(recent_performance)
                },
                'strategy_breakdown': strategy_performance,
                'risk_metrics': {
                    'max_drawdown': max_drawdown,
                    'current_drawdown': self._calculate_current_drawdown(balance_history),
                    'volatility': self._calculate_balance_volatility(balance_history)
                },
                'model_quality': {
                    'prediction_accuracy': prediction_accuracy,
                    'learning_rate': self.learning_rate,
                    'memory_usage': len(self.memory),
                    'training_cycles': len(self.performance_history)
                }
            }
            
            return advanced_stats
            
        except Exception as e:
            self.logger.error(f"Ошибка расчета расширенной статистики: {e}")
            return self.get_statistics()
    
    def _calculate_max_drawdown(self, balance_history: List[float]) -> float:
        """Расчет максимальной просадки"""
        if not balance_history:
            return 0.0
        
        try:
            peak = balance_history[0]
            max_drawdown = 0.0
            
            for balance in balance_history:
                if balance > peak:
                    peak = balance
                drawdown = (peak - balance) / peak if peak > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)
            
            return max_drawdown * 100  # В процентах
        except:
            return 0.0
    
    def _calculate_current_drawdown(self, balance_history: List[float]) -> float:
        """Расчет текущей просадки"""
        if not balance_history:
            return 0.0
        
        try:
            peak = max(balance_history)
            current = balance_history[-1]
            return ((peak - current) / peak * 100) if peak > 0 else 0.0
        except:
            return 0.0
    
    def _calculate_balance_volatility(self, balance_history: List[float]) -> float:
        """Расчет волатильности баланса"""
        if len(balance_history) < 2:
            return 0.0
        
        try:
            returns = [balance_history[i] / balance_history[i-1] - 1 
                      for i in range(1, len(balance_history)) 
                      if balance_history[i-1] > 0]
            return np.std(returns) * 100 if returns else 0.0  # В процентах
        except:
            return 0.0
    
    def _calculate_prediction_accuracy(self) -> float:
        """Расчет точности предсказаний"""
        try:
            if len(self.performance_history) < 10:
                return 0.5
            
            recent = self.performance_history[-100:]  # Последние 100 записей
            correct_predictions = 0
            
            for record in recent:
                # Считаем предсказание правильным, если уверенность была высокой и результат успешный
                # или уверенность была низкой и результат неуспешный
                confidence = record['confidence']
                success = record['success']
                
                if (confidence > 0.6 and success) or (confidence <= 0.6 and not success):
                    correct_predictions += 1
            
            return correct_predictions / len(recent)
        except:
            return 0.5
    
    def get_statistics(self) -> Dict:
        """Базовая статистика нейронной сети"""
        try:
            win_rate = (self.winning_bets / self.total_bets * 100) if self.total_bets > 0 else 0
            roi = ((self.current_balance - 1000.0) / 1000.0 * 100) if self.current_balance > 0 else -100
            
            return {
                'total_bets': self.total_bets,
                'winning_bets': self.winning_bets,
                'win_rate': win_rate,
                'current_balance': self.current_balance,
                'profit': self.current_balance - 1000.0,
                'roi': roi,
                'avg_bet_size': self.bet_amount,
                'confidence_threshold': self.confidence_threshold,
                'memory_size': len(self.memory),
                'model_version': '2.0'
            }
        except Exception as e:
            self.logger.error(f"Ошибка расчета статистики: {e}")
            return {
                'total_bets': 0,
                'winning_bets': 0,
                'win_rate': 0,
                'current_balance': 1000.0,
                'profit': 0,
                'roi': 0
            }
    
    def save_model(self):
        """Сохранение улучшенной модели"""
        try:
            model_data = {
                'version': '2.0',
                'timestamp': datetime.now().isoformat(),
                'architecture': {
                    'input_size': self.input_size,
                    'hidden_size': self.hidden_size,
                    'output_size': self.output_size
                },
                'weights': {
                    'weights1': self.weights1.tolist(),
                    'weights2': self.weights2.tolist(),
                    'weights3': self.weights3.tolist(),
                    'bias1': self.bias1.tolist(),
                    'bias2': self.bias2.tolist(),
                    'bias3': self.bias3.tolist()
                },
                'batch_norm': {
                    'running_mean1': self.running_mean1.tolist(),
                    'running_var1': self.running_var1.tolist(),
                    'running_mean2': self.running_mean2.tolist(),
                    'running_var2': self.running_var2.tolist()
                },
                'hyperparameters': {
                    'learning_rate': self.learning_rate,
                    'l2_lambda': self.l2_lambda,
                    'dropout_rate': self.dropout_rate,
                    'confidence_threshold': self.confidence_threshold
                },
                'statistics': {
                    'total_bets': self.total_bets,
                    'winning_bets': self.winning_bets,
                    'current_balance': self.current_balance,
                    'best_loss': self.best_loss
                },
                'performance_history': self.performance_history[-100:]  # Последние 100 записей
            }
            
            os.makedirs('data/ai', exist_ok=True)
            
            # Сохраняем основную модель
            with open('data/ai/neural_trader_model.json', 'w') as f:
                json.dump(model_data, f, indent=2)
            
            # Создаем бэкап с временной меткой
            backup_filename = f"data/ai/neural_trader_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_filename, 'w') as f:
                json.dump(model_data, f)
            
            # Удаляем старые бэкапы (оставляем только последние 5)
            self._cleanup_old_backups()
            
            self.logger.debug("Модель сохранена успешно")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения модели: {e}")
    
    def _cleanup_old_backups(self):
        """Очистка старых бэкапов модели"""
        try:
            import glob
            backup_files = glob.glob('data/ai/neural_trader_backup_*.json')
            backup_files.sort()  # Сортируем по имени (по времени)
            
            # Удаляем все кроме последних 5
            for old_backup in backup_files[:-5]:
                try:
                    os.remove(old_backup)
                except:
                    pass
        except:
            pass
    
    def load_model(self):
        """Загрузка улучшенной модели с валидацией"""
        model_path = 'data/ai/neural_trader_model.json'
        
        if not os.path.exists(model_path):
            self.logger.info("Файл модели не найден, используем начальную инициализацию")
            return
        
        try:
            with open(model_path, 'r') as f:
                model_data = json.load(f)
            
            # Проверяем версию модели
            version = model_data.get('version', '1.0')
            if version != '2.0':
                self.logger.warning(f"Загружается модель версии {version}, ожидалась 2.0")
            
            # Загружаем веса
            weights = model_data.get('weights', {})
            if weights:
                self.weights1 = np.array(weights['weights1'])
                self.weights2 = np.array(weights['weights2'])
                self.weights3 = np.array(weights['weights3'])
                self.bias1 = np.array(weights['bias1'])
                self.bias2 = np.array(weights['bias2'])
                self.bias3 = np.array(weights['bias3'])
            
            # Загружаем batch normalization параметры
            batch_norm = model_data.get('batch_norm', {})
            if batch_norm:
                self.running_mean1 = np.array(batch_norm.get('running_mean1', self.running_mean1))
                self.running_var1 = np.array(batch_norm.get('running_var1', self.running_var1))
                self.running_mean2 = np.array(batch_norm.get('running_mean2', self.running_mean2))
                self.running_var2 = np.array(batch_norm.get('running_var2', self.running_var2))
            
            # Загружаем гиперпараметры
            hyperparams = model_data.get('hyperparameters', {})
            if hyperparams:
                self.learning_rate = hyperparams.get('learning_rate', self.learning_rate)
                self.l2_lambda = hyperparams.get('l2_lambda', self.l2_lambda)
                self.dropout_rate = hyperparams.get('dropout_rate', self.dropout_rate)
                self.confidence_threshold = hyperparams.get('confidence_threshold', self.confidence_threshold)
            
            # Загружаем статистику
            statistics = model_data.get('statistics', {})
            if statistics:
                self.total_bets = statistics.get('total_bets', 0)
                self.winning_bets = statistics.get('winning_bets', 0)
                self.current_balance = statistics.get('current_balance', 1000.0)
                self.best_loss = statistics.get('best_loss', float('inf'))
            
            # Загружаем историю производительности
            self.performance_history = model_data.get('performance_history', [])
            
            # Валидация загруженных данных
            self._validate_loaded_model()
            
            win_rate = (self.winning_bets / self.total_bets * 100) if self.total_bets > 0 else 0
            self.logger.info(f"Модель загружена: Баланс ${self.current_balance:.2f}, "
                           f"Ставок: {self.total_bets}, Винрейт: {win_rate:.1f}%")
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки модели: {e}")
            self.logger.info("Используем начальную инициализацию")
    
    def _validate_loaded_model(self):
        """Валидация загруженной модели"""
        try:
            # Проверяем размерности весов
            assert self.weights1.shape == (self.input_size, self.hidden_size)
            assert self.weights2.shape == (self.hidden_size, self.hidden_size)
            assert self.weights3.shape == (self.hidden_size, self.output_size)
            
            # Проверяем на NaN и Inf
            for weights in [self.weights1, self.weights2, self.weights3]:
                if np.any(np.isnan(weights)) or np.any(np.isinf(weights)):
                    raise ValueError("Обнаружены NaN или Inf в весах")
            
            # Проверяем разумность значений
            if self.current_balance < 0 or self.current_balance > 1000000:
                self.logger.warning(f"Подозрительное значение баланса: {self.current_balance}")
                self.current_balance = max(0, min(self.current_balance, 10000))
            
            if self.total_bets < 0 or self.winning_bets < 0 or self.winning_bets > self.total_bets:
                self.logger.warning("Некорректная статистика ставок, сбрасываем")
                self.total_bets = 0
                self.winning_bets = 0
            
        except Exception as e:
            self.logger.error(f"Ошибка валидации модели: {e}")
            # Переинициализируем веса в случае ошибки
            self.__init__(self.input_size, self.hidden_size, self.output_size, 
                         self.initial_lr, self.memory_size, self.l2_lambda, self.dropout_rate)
    
    def reset_model(self):
        """Сброс модели к начальному состоянию"""
        self.logger.info("Сброс нейронной модели к начальному состоянию")
        
        # Переинициализируем веса
        self.weights1 = np.random.randn(self.input_size, self.hidden_size) * np.sqrt(2.0 / self.input_size)
        self.weights2 = np.random.randn(self.hidden_size, self.hidden_size) * np.sqrt(2.0 / self.hidden_size)
        self.weights3 = np.random.randn(self.hidden_size, self.output_size) * np.sqrt(2.0 / self.hidden_size)
        
        # Сбрасываем смещения
        self.bias1 = np.zeros((1, self.hidden_size))
        self.bias2 = np.zeros((1, self.hidden_size))
        self.bias3 = np.zeros((1, self.output_size))
        
        # Сбрасываем batch normalization
        self.running_mean1 = np.zeros((1, self.hidden_size))
        self.running_var1 = np.ones((1, self.hidden_size))
        self.running_mean2 = np.zeros((1, self.hidden_size))
        self.running_var2 = np.ones((1, self.hidden_size))
        
        # Сбрасываем статистику
        self.total_bets = 0
        self.winning_bets = 0
        self.current_balance = 1000.0
        self.memory = []
        self.performance_history = []
        
        # Сбрасываем параметры обучения
        self.learning_rate = self.initial_lr
        self.best_loss = float('inf')
        self.no_improve_count = 0
        
        # Сохраняем сброшенную модель
        self.save_model()
    
    def _calculate_trend_strength(self, market_data: Dict) -> float:
        """Расчет силы тренда по нескольким таймфреймам"""
        try:
            trend_signals = []
            for tf in ['5m', '15m', '1h']:
                if (tf in market_data and market_data[tf] is not None and not market_data[tf].empty):
                    df = market_data[tf].tail(50)
                    if len(df) >= 20:
                        # ADX-like trend strength
                        high, low, close = df['high'], df['low'], df['close']
                        plus_dm = np.maximum(high.diff(), 0)
                        minus_dm = np.maximum(-low.diff(), 0)
                        tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
                        
                        plus_di = 100 * (plus_dm.rolling(14).mean() / tr.rolling(14).mean())
                        minus_di = 100 * (minus_dm.rolling(14).mean() / tr.rolling(14).mean())
                        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
                        adx = dx.rolling(14).mean().iloc[-1]
                        
                        if not np.isnan(adx):
                            # Нормализуем ADX от 0-100 к -1,1
                            trend_direction = 1 if plus_di.iloc[-1] > minus_di.iloc[-1] else -1
                            trend_signals.append(trend_direction * (adx / 100))
            
            return np.mean(trend_signals) if trend_signals else 0.0
        except:
            return 0.0
    
    def _calculate_momentum_divergence(self, market_data: Dict) -> float:
        """Обнаружение дивергенций моментума"""
        try:
            for tf in ['15m', '1h']:
                if (tf in market_data and market_data[tf] is not None and not market_data[tf].empty):
                    df = market_data[tf].tail(50)
                    if len(df) >= 14:
                        close = df['close']
                        # RSI calculation
                        delta = close.diff()
                        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                        rs = gain / loss
                        rsi = 100 - (100 / (1 + rs))
                        
                        # Простая дивергенция: сравниваем направление цены и RSI
                        price_trend = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10]
                        rsi_trend = (rsi.iloc[-1] - rsi.iloc[-10]) / 100
                        
                        # Дивергенция: когда цена и RSI движутся в разные стороны
                        if (price_trend > 0 and rsi_trend < 0) or (price_trend < 0 and rsi_trend > 0):
                            return abs(price_trend - rsi_trend)  # Положительная дивергенция
                        else:
                            return 0.0
            return 0.0
        except:
            return 0.0
    
    def _calculate_volume_profile(self, market_data: Dict) -> float:
        """Анализ объемного профиля"""
        try:
            for tf in ['5m', '15m']:
                if (tf in market_data and market_data[tf] is not None and not market_data[tf].empty):
                    df = market_data[tf].tail(100)
                    if len(df) >= 20:
                        # VWAP и отклонение от него
                        typical_price = (df['high'] + df['low'] + df['close']) / 3
                        vwap = (typical_price * df['volume']).sum() / df['volume'].sum()
                        current_price = df['close'].iloc[-1]
                        
                        # On-Balance Volume trend
                        obv = np.where(df['close'] > df['close'].shift(1), df['volume'], 
                                      np.where(df['close'] < df['close'].shift(1), -df['volume'], 0)).cumsum()
                        obv_trend = (obv[-1] - obv[-10]) / (abs(obv[-10]) + 1e-8)
                        
                        # Комбинируем VWAP дистанцию и OBV тренд
                        vwap_distance = (current_price - vwap) / vwap
                        return np.clip(abs(vwap_distance) + abs(obv_trend) * 0.1, 0, 2)
            return 0.0
        except:
            return 0.0
    
    def _calculate_timeframe_correlation(self, market_data: Dict) -> float:
        """Корреляция между таймфреймами"""
        try:
            timeframes = ['5m', '15m', '1h']
            returns_data = []
            
            for tf in timeframes:
                if (tf in market_data and market_data[tf] is not None and not market_data[tf].empty):
                    df = market_data[tf].tail(50)
                    if len(df) > 1:
                        returns = df['close'].pct_change().dropna()
                        if len(returns) >= 10:
                            returns_data.append(returns.iloc[-10:].values)  # Последние 10 возвратов
            
            if len(returns_data) >= 2:
                # Средняя корреляция между всеми парами таймфреймов
                correlations = []
                for i in range(len(returns_data)):
                    for j in range(i + 1, len(returns_data)):
                        min_len = min(len(returns_data[i]), len(returns_data[j]))
                        if min_len > 3:
                            corr = np.corrcoef(returns_data[i][:min_len], returns_data[j][:min_len])[0, 1]
                            if not np.isnan(corr):
                                correlations.append(corr)
                
                return np.mean(correlations) if correlations else 0.0
            return 0.0
        except:
            return 0.0
    
    def _calculate_spread_dynamics(self, market_data: Dict) -> float:
        """Динамика спреда (bid-ask)"""
        try:
            # Приближаем спред через high-low в минутных данных
            for tf in ['1m', '5m']:
                if (tf in market_data and market_data[tf] is not None and not market_data[tf].empty):
                    df = market_data[tf].tail(20)
                    if len(df) > 1:
                        spreads = (df['high'] - df['low']) / df['close']
                        spread_volatility = spreads.std()
                        avg_spread = spreads.mean()
                        return np.clip(avg_spread + spread_volatility, 0, 1)
            return 0.5
        except:
            return 0.5
    
    def _calculate_order_flow_imbalance(self, market_data: Dict) -> float:
        """Небаланс ордерфлоу (приблизительно)"""
        try:
            for tf in ['1m', '5m']:
                if (tf in market_data and market_data[tf] is not None and not market_data[tf].empty):
                    df = market_data[tf].tail(20)
                    if len(df) > 1:
                        # Простое приближение: сравниваем объем на росте и падении
                        up_volume = df[df['close'] > df['open']]['volume'].sum()
                        down_volume = df[df['close'] < df['open']]['volume'].sum()
                        total_volume = up_volume + down_volume
                        
                        if total_volume > 0:
                            imbalance = (up_volume - down_volume) / total_volume
                            return np.clip(imbalance, -1, 1)
            return 0.0
        except:
            return 0.0
    
    def _extract_temporal_features(self) -> List[float]:
        """Извлечение временных признаков"""
        try:
            now = datetime.now()
            
            # Циклическая кодировка времени (синус и косинус)
            hour_sin = np.sin(2 * np.pi * now.hour / 24)
            hour_cos = np.cos(2 * np.pi * now.hour / 24)
            
            day_of_week_sin = np.sin(2 * np.pi * now.weekday() / 7)
            day_of_week_cos = np.cos(2 * np.pi * now.weekday() / 7)
            
            # Торговые сессии (приблизительно)
            asian_session = 1.0 if 0 <= now.hour <= 8 else 0.0
            european_session = 1.0 if 8 <= now.hour <= 16 else 0.0
            american_session = 1.0 if 16 <= now.hour <= 24 else 0.0
            
            # Особые временные окна
            weekend_factor = 0.5 if now.weekday() >= 5 else 1.0
            
            return [
                hour_sin, hour_cos, day_of_week_sin, day_of_week_cos,
                asian_session, european_session, american_session, weekend_factor
            ]
        except:
            return [0.0] * 8