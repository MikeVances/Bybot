# bot/services/market_data_service.py
"""
📊 СЕРВИС РЫНОЧНЫХ ДАННЫХ
Централизованное получение и обработка рыночных данных
"""

import pandas as pd
from typing import Dict, Optional, Any
from bot.core.secure_logger import get_secure_logger


class MarketDataService:
    """
    📊 Сервис для работы с рыночными данными
    """
    
    def __init__(self):
        """Инициализация сервиса рыночных данных"""
        self.logger = get_secure_logger('market_data_service')
        self.timeframes = {
            '1m': "1",
            '5m': "5", 
            '15m': "15",
            '1h': "60"
        }
    
    def get_all_timeframes_data(self, api) -> Dict[str, pd.DataFrame]:
        """
        Получение данных по всем таймфреймам
        
        Args:
            api: API экземпляр для получения данных
            
        Returns:
            Dict: Словарь с данными по каждому таймфрейму
        """
        all_market_data = {}
        
        for tf_name, tf_value in self.timeframes.items():
            try:
                df = api.get_ohlcv(interval=tf_value, limit=200)
                if df is not None and not df.empty:
                    all_market_data[tf_name] = df
                    self.logger.debug(f"📊 Получены данные {tf_name}: {len(df)} свечей")
                else:
                    self.logger.warning(f"⚠️ Нет данных для {tf_name}")
                    
            except Exception as e:
                self.logger.error(f"❌ Ошибка получения данных {tf_name}: {e}")
                continue
        
        if all_market_data:
            self.logger.info(f"✅ Загружены данные по {len(all_market_data)} таймфреймам")
        else:
            self.logger.error("❌ Не удалось получить рыночные данные")
        
        return all_market_data
    
    def get_current_price(self, api, symbol: str = "BTCUSDT") -> Optional[float]:
        """
        Получение текущей цены инструмента
        
        Args:
            api: API экземпляр
            symbol: Торговый инструмент
            
        Returns:
            float: Текущая цена или None
        """
        try:
            df = api.get_ohlcv(symbol=symbol, interval="1", limit=1)
            if df is not None and not df.empty:
                current_price = float(df.iloc[-1]['close'])
                self.logger.debug(f"💰 Текущая цена {symbol}: ${current_price:,.2f}")
                return current_price
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения цены {symbol}: {e}")
            
        return None
    
    def validate_market_data(self, market_data: Dict[str, pd.DataFrame]) -> bool:
        """
        Валидация рыночных данных
        
        Args:
            market_data: Рыночные данные для валидации
            
        Returns:
            bool: True если данные валидны
        """
        if not market_data:
            self.logger.error("❌ Рыночные данные отсутствуют")
            return False
        
        required_timeframes = ['1m', '5m']
        for tf in required_timeframes:
            if tf not in market_data or market_data[tf].empty:
                self.logger.error(f"❌ Отсутствуют данные для обязательного таймфрейма: {tf}")
                return False
        
        # Проверяем актуальность данных (не старше 5 минут)
        try:
            latest_1m = pd.to_datetime(market_data['1m'].iloc[-1]['timestamp'])
            current_time = pd.Timestamp.now(tz='UTC')
            time_diff = (current_time - latest_1m).total_seconds()
            
            if time_diff > 300:  # 5 минут
                self.logger.warning(f"⚠️ Данные устарели: {time_diff:.0f} сек назад")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки актуальности данных: {e}")
            return False
        
        self.logger.debug("✅ Рыночные данные валидны")
        return True
    
    def calculate_market_metrics(self, market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Расчет основных рыночных метрик
        
        Args:
            market_data: Рыночные данные
            
        Returns:
            Dict: Рассчитанные метрики
        """
        metrics = {}
        
        try:
            if '1h' in market_data and not market_data['1h'].empty:
                hourly = market_data['1h']
                
                # Волатильность (24ч)
                if len(hourly) >= 24:
                    last_24h = hourly.tail(24)
                    volatility = (last_24h['high'].max() - last_24h['low'].min()) / last_24h['close'].mean() * 100
                    metrics['volatility_24h'] = round(volatility, 2)
                
                # Тренд (6ч)
                if len(hourly) >= 6:
                    last_6h = hourly.tail(6)
                    price_change = (last_6h.iloc[-1]['close'] - last_6h.iloc[0]['close']) / last_6h.iloc[0]['close'] * 100
                    metrics['trend_6h'] = round(price_change, 2)
            
            if '1m' in market_data and not market_data['1m'].empty:
                minute = market_data['1m']
                
                # Текущая цена
                metrics['current_price'] = float(minute.iloc[-1]['close'])
                
                # Объем (1ч)
                if len(minute) >= 60:
                    last_hour_volume = minute.tail(60)['volume'].sum()
                    metrics['volume_1h'] = float(last_hour_volume)
            
            self.logger.debug(f"📊 Рассчитаны метрики: {list(metrics.keys())}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета метрик: {e}")
        
        return metrics


# Глобальный экземпляр сервиса
_market_data_service = None


def get_market_data_service():
    """
    Получение глобального экземпляра сервиса рыночных данных
    
    Returns:
        MarketDataService: Экземпляр сервиса
    """
    global _market_data_service
    
    if _market_data_service is None:
        _market_data_service = MarketDataService()
    
    return _market_data_service