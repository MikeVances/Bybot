"""
Простая MVP стратегия для тестирования системы
Базовая стратегия на основе SMA кроссовера
"""

import logging
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SimpleMVPStrategy:
    """
    Простая MVP стратегия для тестирования

    Стратегия:
    - Покупка при пересечении SMA(9) выше SMA(21)
    - Продажа при пересечении SMA(9) ниже SMA(21)
    - Простой стоп-лосс и тейк-профит
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.name = "SimpleMVP"
        self.version = "1.0.0"

        # Параметры стратегии
        self.fast_period = self.config.get('fast_period', 9)
        self.slow_period = self.config.get('slow_period', 21)
        self.stop_loss_pct = self.config.get('stop_loss_pct', 2.0)
        self.take_profit_pct = self.config.get('take_profit_pct', 3.0)

        # Состояние
        self.last_signal = None
        self.last_signal_time = None

        logger.info(f"🚀 Инициализирована {self.name} v{self.version}")
        logger.info(f"📊 SMA: fast={self.fast_period}, slow={self.slow_period}")
        logger.info(f"🎯 SL={self.stop_loss_pct}%, TP={self.take_profit_pct}%")

    def analyze(self, df: pd.DataFrame, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Анализ рыночных данных и генерация сигналов

        Args:
            df: DataFrame с OHLCV данными

        Returns:
            Dict с сигналом или None
        """
        try:
            if len(df) < self.slow_period + 1:
                logger.debug(f"Недостаточно данных: {len(df)} < {self.slow_period + 1}")
                return None

            # Рассчитываем индикаторы
            df = df.copy()
            df['sma_fast'] = df['close'].rolling(window=self.fast_period).mean()
            df['sma_slow'] = df['close'].rolling(window=self.slow_period).mean()

            # Берем последние значения
            current = df.iloc[-1]
            previous = df.iloc[-2]

            current_price = float(current['close'])
            sma_fast_curr = float(current['sma_fast'])
            sma_slow_curr = float(current['sma_slow'])
            sma_fast_prev = float(previous['sma_fast'])
            sma_slow_prev = float(previous['sma_slow'])

            # Проверяем валидность данных
            if pd.isna(sma_fast_curr) or pd.isna(sma_slow_curr):
                logger.debug("Индикаторы не готовы (NaN значения)")
                return None

            signal_type = None
            signal_strength = 0.0

            # Логика сигналов: кроссовер SMA
            # Бычий сигнал: fast SMA пересекает slow SMA снизу вверх
            if (sma_fast_prev <= sma_slow_prev and
                sma_fast_curr > sma_slow_curr):
                signal_type = 'BUY'
                signal_strength = abs(sma_fast_curr - sma_slow_curr) / sma_slow_curr

            # Медвежий сигнал: fast SMA пересекает slow SMA сверху вниз
            elif (sma_fast_prev >= sma_slow_prev and
                  sma_fast_curr < sma_slow_curr):
                signal_type = 'SELL'
                signal_strength = abs(sma_fast_curr - sma_slow_curr) / sma_slow_curr

            if signal_type:
                # Рассчитываем уровни
                stop_loss = current_price * (1 - self.stop_loss_pct/100) if signal_type == 'BUY' else current_price * (1 + self.stop_loss_pct/100)
                take_profit = current_price * (1 + self.take_profit_pct/100) if signal_type == 'BUY' else current_price * (1 - self.take_profit_pct/100)

                signal = {
                    'strategy': self.name,
                    'signal': signal_type,
                    'price': current_price,
                    'timestamp': datetime.now(),
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'strength': min(signal_strength * 100, 1.0),  # Нормализуем до 0-1
                    'indicators': {
                        'sma_fast': sma_fast_curr,
                        'sma_slow': sma_slow_curr,
                        'crossover': f"{self.fast_period}>{self.slow_period}" if signal_type == 'BUY' else f"{self.fast_period}<{self.slow_period}"
                    },
                    'confidence': 0.7,  # Базовая уверенность для MVP
                    'trade_amount': self.config.get('trade_amount', 0.001)
                }

                self.last_signal = signal_type
                self.last_signal_time = datetime.now()

                logger.info(f"🎯 {signal_type} сигнал: цена={current_price:.2f}, сила={signal_strength:.3f}")
                logger.info(f"📊 SMA: fast={sma_fast_curr:.2f}, slow={sma_slow_curr:.2f}")

                return signal

            # Нет сигнала
            logger.debug(f"Нет сигнала: SMA fast={sma_fast_curr:.2f}, slow={sma_slow_curr:.2f}")
            return None

        except Exception as e:
            logger.error(f"❌ Ошибка анализа MVP стратегии: {e}")
            return None

    def get_required_history(self) -> int:
        """Возвращает необходимое количество баров для анализа"""
        return self.slow_period + 5  # +5 для надежности

    def get_status(self) -> Dict[str, Any]:
        """Возвращает статус стратегии"""
        return {
            'name': self.name,
            'version': self.version,
            'last_signal': self.last_signal,
            'last_signal_time': self.last_signal_time.isoformat() if self.last_signal_time else None,
            'parameters': {
                'fast_period': self.fast_period,
                'slow_period': self.slow_period,
                'stop_loss_pct': self.stop_loss_pct,
                'take_profit_pct': self.take_profit_pct
            }
        }


def create_strategy(config: Dict[str, Any] = None) -> SimpleMVPStrategy:
    """Фабричная функция для создания стратегии"""
    return SimpleMVPStrategy(config)


# Экспорт для совместимости с существующей системой
class VolumeVWAP:
    """Заглушка для совместимости с существующим кодом"""
    def __init__(self, **kwargs):
        self.strategy = SimpleMVPStrategy(kwargs)

    def analyze(self, df, **kwargs):
        return self.strategy.analyze(df, **kwargs)


class CumDeltaSR:
    """Заглушка для совместимости с существующим кодом"""
    def __init__(self, **kwargs):
        self.strategy = SimpleMVPStrategy(kwargs)

    def analyze(self, df, **kwargs):
        return self.strategy.analyze(df, **kwargs)


class MultiTFVolume:
    """Заглушка для совместимости с существующим кодом"""
    def __init__(self, **kwargs):
        self.strategy = SimpleMVPStrategy(kwargs)

    def analyze(self, df, **kwargs):
        return self.strategy.analyze(df, **kwargs)