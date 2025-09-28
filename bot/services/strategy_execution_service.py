# bot/services/strategy_execution_service.py
"""
🎯 СЕРВИС ВЫПОЛНЕНИЯ СТРАТЕГИЙ
Централизованное выполнение торговых стратегий
"""

import importlib
from typing import Dict, List, Any, Optional
from bot.core.secure_logger import get_secure_logger
from config import get_strategy_config


class StrategyExecutionService:
    """
    🎯 Сервис для выполнения торговых стратегий
    """
    
    def __init__(self):
        """Инициализация сервиса выполнения стратегий"""
        self.logger = get_secure_logger('strategy_execution')
        self.loaded_strategies = {}
    
    def load_strategy_modules(self, enabled_strategies: List[str]) -> Dict[str, Any]:
        """
        Загрузка модулей стратегий
        
        Args:
            enabled_strategies: Список включенных стратегий
            
        Returns:
            Dict: Словарь загруженных стратегий
        """
        loaded_strategies = {}
        
        for strategy_name in enabled_strategies:
            try:
                config = get_strategy_config(strategy_name)
                
                if not config.get('enabled', True):
                    self.logger.info(f"⏸️ Стратегия {strategy_name} отключена в конфигурации")
                    continue
                
                # Маппинг названий конфигураций стратегий к файлам модулей
                strategy_mapping = {
                    'volume_vwap_default': 'volume_vwap_strategy_v3',
                    'volume_vwap_conservative': 'volume_vwap_strategy_v3',
                    'cumdelta_sr_default': 'cumdelta_sr_strategy_v3',
                    'multitf_volume_default': 'multitf_volume_strategy_v3',
                    'fibonacci_rsi_default': 'fibonacci_rsi_strategy_v3',
                    'range_trading_default': 'range_trading_strategy_v3'
                }

                module_name = strategy_mapping.get(strategy_name, strategy_name.lower())
                strategy_module = importlib.import_module(f'bot.strategy.implementations.{module_name}')
                loaded_strategies[strategy_name] = {
                    'module': strategy_module,
                    'config': config,
                    'description': config.get('description', 'Без описания')
                }
                
                self.logger.info(f"✅ Загружена стратегия {strategy_name}: {config['description']}")
                
            except ImportError as e:
                self.logger.error(f"❌ Не найден модуль стратегии {strategy_name}: {e}")
                continue
            except Exception as e:
                self.logger.error(f"❌ Ошибка загрузки стратегии {strategy_name}: {e}")
                continue
        
        self.loaded_strategies = loaded_strategies
        self.logger.info(f"📚 Загружено стратегий: {len(loaded_strategies)}")
        return loaded_strategies
    
    def execute_strategy(self, strategy_name: str, market_data: Dict[str, Any], 
                        balance: float, state) -> Optional[Dict[str, Any]]:
        """
        Выполнение конкретной стратегии
        
        Args:
            strategy_name: Название стратегии
            market_data: Рыночные данные
            balance: Текущий баланс
            state: Состояние стратегии
            
        Returns:
            Dict: Торговый сигнал или None
        """
        if strategy_name not in self.loaded_strategies:
            self.logger.error(f"❌ Стратегия {strategy_name} не загружена")
            return None
        
        try:
            strategy_info = self.loaded_strategies[strategy_name]
            strategy_module = strategy_info['module']
            config = strategy_info['config']
            
            # Проверяем, есть ли функция execute_strategy в модуле
            if not hasattr(strategy_module, 'execute_strategy'):
                self.logger.error(f"❌ В стратегии {strategy_name} нет функции execute_strategy")
                return None
            
            # Выполняем стратегию
            signal = strategy_module.execute_strategy(
                market_data=market_data,
                balance=balance,
                config=config,
                bot_state=state
            )

            if signal:
                if 'signal_type' not in signal and 'signal' in signal:
                    signal['signal_type'] = signal['signal']
                # Добавляем метаданные к сигналу
                signal['strategy'] = strategy_name
                signal['timestamp'] = market_data.get('timestamp')

                self.logger.info(f"🎯 Стратегия {strategy_name} сгенерировала сигнал: {signal.get('signal_type', 'UNKNOWN')}")
                
                # Валидируем сигнал
                if self._validate_signal(signal):
                    return signal
                else:
                    self.logger.warning(f"⚠️ Невалидный сигнал от стратегии {strategy_name}")
                    return None
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения стратегии {strategy_name}: {e}")
        
        return None
    
    def execute_all_strategies(self, active_strategies: List[str], 
                             all_market_data: Dict[str, Any], 
                             strategy_states: Dict[str, Any],
                             get_balance_func) -> Dict[str, Any]:
        """
        Выполнение всех активных стратегий
        
        Args:
            active_strategies: Список активных стратегий
            all_market_data: Все рыночные данные
            strategy_states: Состояния стратегий
            get_balance_func: Функция получения баланса
            
        Returns:
            Dict: Словарь сигналов от стратегий
        """
        strategy_signals = {}
        
        for strategy_name in active_strategies:
            try:
                if strategy_name not in strategy_states:
                    self.logger.warning(f"⚠️ Нет состояния для стратегии {strategy_name}")
                    continue
                
                state = strategy_states[strategy_name]
                
                # Получаем текущий баланс для стратегии
                current_balance = get_balance_func(strategy_name)
                
                # Выполняем стратегию
                signal = self.execute_strategy(
                    strategy_name, all_market_data, current_balance, state
                )
                
                if signal:
                    strategy_signals[strategy_name] = signal
                    self.logger.debug(f"📊 Сигнал {strategy_name}: {signal['signal_type']}")
                
            except Exception as e:
                self.logger.error(f"❌ Ошибка выполнения стратегии {strategy_name}: {e}")
                continue
        
        if strategy_signals:
            self.logger.info(f"🎯 Получено сигналов: {len(strategy_signals)}")
        
        return strategy_signals
    
    def _validate_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Валидация торгового сигнала
        
        Args:
            signal: Торговый сигнал для валидации
            
        Returns:
            bool: True если сигнал валиден
        """
        required_fields = ['signal_type']
        
        # Проверяем обязательные поля
        for field in required_fields:
            if field not in signal:
                self.logger.error(f"❌ Отсутствует обязательное поле в сигнале: {field}")
                return False
        
        # Проверяем тип сигнала
        valid_signal_types = [
            'ENTER_LONG', 'ENTER_SHORT', 'EXIT_LONG', 'EXIT_SHORT',
            'BUY', 'SELL', 'HOLD'
        ]
        
        if signal['signal_type'] not in valid_signal_types:
            self.logger.error(f"❌ Невалидный тип сигнала: {signal['signal_type']}")
            return False
        
        # Для сигналов входа проверяем дополнительные поля
        if signal['signal_type'] in {'ENTER_LONG', 'ENTER_SHORT', 'BUY', 'SELL'}:
            if 'entry_price' not in signal and 'stop_loss' not in signal:
                self.logger.warning("⚠️ Отсутствуют цена входа или стоп-лосс")
        
        return True
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """
        Получение статуса всех загруженных стратегий
        
        Returns:
            Dict: Статус стратегий
        """
        status = {
            'total_strategies': len(self.loaded_strategies),
            'strategies': {}
        }
        
        for name, info in self.loaded_strategies.items():
            status['strategies'][name] = {
                'loaded': True,
                'description': info['description'],
                'enabled': info['config'].get('enabled', True)
            }
        
        return status
    
    def reload_strategy(self, strategy_name: str) -> bool:
        """
        Перезагрузка конкретной стратегии
        
        Args:
            strategy_name: Название стратегии для перезагрузки
            
        Returns:
            bool: True если перезагрузка успешна
        """
        try:
            if strategy_name in self.loaded_strategies:
                # Удаляем старую версию
                del self.loaded_strategies[strategy_name]
            
            # Загружаем заново
            new_strategies = self.load_strategy_modules([strategy_name])
            
            if strategy_name in new_strategies:
                self.logger.info(f"🔄 Стратегия {strategy_name} успешно перезагружена")
                return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка перезагрузки стратегии {strategy_name}: {e}")
        
        return False


# Глобальный экземпляр сервиса
_strategy_service = None


def get_strategy_service():
    """
    Получение глобального экземпляра сервиса выполнения стратегий
    
    Returns:
        StrategyExecutionService: Экземпляр сервиса
    """
    global _strategy_service
    
    if _strategy_service is None:
        _strategy_service = StrategyExecutionService()
    
    return _strategy_service
