# bot/core/trader_orchestrator.py
"""
🎼 ТОРГОВЫЙ ОРКЕСТРАТОР
Новая архитектура: координация всех сервисов вместо монолитной функции
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import threading

from bot.exchange.api_adapter import create_trading_bot_adapter
from bot.ai import NeuralIntegration
from bot.risk import RiskManager
from config import get_strategy_config, ACTIVE_STRATEGIES, USE_TESTNET

# Алиас для совместимости
ENABLED_STRATEGIES = ACTIVE_STRATEGIES

# Импорты сервисов
from bot.services.notification_service import get_notification_service
from bot.services.market_data_service import get_market_data_service
from bot.services.position_management_service import get_position_service
from bot.services.strategy_execution_service import get_strategy_service

# Импорты безопасности
from bot.core.secure_logger import get_secure_logger
from bot.core.thread_safe_state import get_bot_state


class TradingOrchestrator:
    """
    🎼 Оркестратор торговых операций
    Координирует работу всех сервисов
    """
    
    def __init__(self, telegram_bot=None, neural_integration=None):
        """
        Инициализация оркестратора
        
        Args:
            telegram_bot: Экземпляр Telegram бота
            neural_integration: Экземпляр нейронной интеграции
        """
        self.logger = get_secure_logger('trading_orchestrator')
        
        # Инициализация сервисов
        self.notification_service = get_notification_service(telegram_bot)
        self.market_service = get_market_data_service()
        self.position_service = get_position_service()
        self.strategy_service = get_strategy_service()
        
        # Торговые компоненты
        self.risk_manager = RiskManager()
        self.neural_integration = neural_integration
        
        # Состояние системы
        self.strategy_apis = {}
        self.strategy_states = {}
        self.strategy_loggers = {}
        
        self.logger.info("🎼 Торговый оркестратор инициализирован")
    
    def initialize_strategies(self) -> bool:
        """
        Инициализация стратегий и API соединений
        
        Returns:
            bool: True если инициализация успешна
        """
        try:
            self.logger.info(f"🔄 Инициализация {len(ENABLED_STRATEGIES)} стратегий...")
            
            # Загружаем модули стратегий
            loaded_strategies = self.strategy_service.load_strategy_modules(ENABLED_STRATEGIES)
            
            if not loaded_strategies:
                self.logger.error("❌ Нет доступных стратегий!")
                return False
            
            # Инициализируем API для каждой стратегии
            for strategy_name in ENABLED_STRATEGIES:
                if not self._initialize_strategy_api(strategy_name):
                    continue
            
            if not self.strategy_apis:
                self.logger.error("❌ Не удалось инициализировать ни одной стратегии!")
                return False
            
            self.logger.info(f"✅ Инициализировано стратегий: {len(self.strategy_apis)}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации стратегий: {e}")
            return False
    
    def _initialize_strategy_api(self, strategy_name: str) -> bool:
        """
        Инициализация API для конкретной стратегии
        
        Args:
            strategy_name: Название стратегии
            
        Returns:
            bool: True если инициализация успешна
        """
        try:
            config = get_strategy_config(strategy_name)
            
            if not config.get('enabled', True):
                self.logger.info(f"⏸️ Стратегия {strategy_name} отключена")
                return False
            
            # Создаем API адаптер
            self.strategy_apis[strategy_name] = create_trading_bot_adapter(
                symbol="BTCUSDT",
                api_key=config['api_key'],
                api_secret=config['api_secret'],
                uid=config.get('uid'),
                testnet=USE_TESTNET
            )
            
            # Инициализируем состояние
            self.strategy_states[strategy_name] = BotState()
            
            self.logger.info(f"✅ Стратегия {strategy_name} инициализирована")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации {strategy_name}: {e}")
            return False
    
    def run_trading_cycle(self, shutdown_event: threading.Event) -> None:
        """
        Основной торговый цикл
        
        Args:
            shutdown_event: Событие для остановки
        """
        iteration_count = 0
        last_sync_time = datetime.now()
        
        self.logger.info("🚀 Запуск торгового цикла с сервисной архитектурой")
        
        while not shutdown_event.is_set():
            try:
                iteration_count += 1
                current_time = datetime.now()
                
                self.logger.info(f"🔄 Итерация #{iteration_count} - {current_time.strftime('%H:%M:%S')}")
                
                # Проверяем аварийный стоп
                if self.risk_manager.emergency_stop:
                    self.logger.warning("⛔ Аварийный стоп активен")
                    shutdown_event.wait(60)
                    continue
                
                # Периодическая синхронизация позиций
                if self._should_sync_positions(current_time, last_sync_time):
                    self._sync_all_positions()
                    last_sync_time = current_time
                
                # Получаем активные стратегии
                active_strategies = self._get_active_strategies()
                if not active_strategies:
                    self.logger.warning("⚠️ Нет активных стратегий")
                    shutdown_event.wait(60)
                    continue
                
                # Получаем рыночные данные
                market_data = self._get_market_data(active_strategies[0])
                if not market_data:
                    self.logger.warning("⚠️ Нет рыночных данных")
                    shutdown_event.wait(30)
                    continue
                
                # Выполняем стратегии
                strategy_signals = self._execute_strategies(active_strategies, market_data)
                
                # Обрабатываем сигналы
                self._process_signals(strategy_signals, market_data)
                
                # Обработка нейронной сети
                if self.neural_integration and strategy_signals:
                    self._process_neural_recommendations(market_data, strategy_signals)
                
                # Пауза между итерациями
                shutdown_event.wait(10)
                
            except Exception as e:
                self.logger.error(f"❌ Ошибка в торговом цикле: {e}")
                shutdown_event.wait(30)
    
    def _should_sync_positions(self, current_time: datetime, last_sync: datetime) -> bool:
        """Проверка необходимости синхронизации позиций"""
        return (current_time - last_sync).total_seconds() > 300  # 5 минут
    
    def _sync_all_positions(self) -> None:
        """Синхронизация всех позиций с биржей"""
        self.logger.info("🔄 Синхронизация позиций с биржей...")
        
        for strategy_name, api in self.strategy_apis.items():
            try:
                state = self.strategy_states[strategy_name]
                self.position_service.sync_position_with_exchange(api, state)
            except Exception as e:
                self.logger.error(f"❌ Ошибка синхронизации {strategy_name}: {e}")
    
    def _get_active_strategies(self) -> List[str]:
        """Получение списка активных стратегий"""
        active_strategies = []
        
        for strategy_name, api in self.strategy_apis.items():
            try:
                # Проверяем блокировку риск-менеджером
                if strategy_name in self.risk_manager.blocked_strategies:
                    continue
                
                # Проверяем баланс
                current_balance = self._get_current_balance(api)
                if current_balance >= 10:  # Минимум для торговли
                    active_strategies.append(strategy_name)
                    
            except Exception as e:
                self.logger.error(f"❌ Ошибка проверки стратегии {strategy_name}: {e}")
        
        return active_strategies
    
    def _get_current_balance(self, api) -> float:
        """Получение текущего баланса"""
        try:
            balance_data = api.get_wallet_balance_v5()
            if balance_data and balance_data.get('retCode') == 0:
                return float(balance_data['result']['list'][0]['totalAvailableBalance'])
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения баланса: {e}")
        
        return 0.0
    
    def _get_market_data(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Получение рыночных данных"""
        try:
            api = self.strategy_apis[strategy_name]
            market_data = self.market_service.get_all_timeframes_data(api)
            
            if self.market_service.validate_market_data(market_data):
                return market_data
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения рыночных данных: {e}")
        
        return None
    
    def _execute_strategies(self, active_strategies: List[str], 
                          market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение всех активных стратегий"""
        return self.strategy_service.execute_all_strategies(
            active_strategies=active_strategies,
            all_market_data=market_data,
            strategy_states=self.strategy_states,
            get_balance_func=lambda name: self._get_current_balance(self.strategy_apis[name])
        )
    
    def _process_signals(self, strategy_signals: Dict[str, Any], 
                        market_data: Dict[str, Any]) -> None:
        """Обработка торговых сигналов"""
        current_price = self.market_service.get_current_price(
            list(self.strategy_apis.values())[0]
        )
        
        if not current_price:
            self.logger.error("❌ Не удалось получить текущую цену")
            return
        
        for strategy_name, signal in strategy_signals.items():
            try:
                self._process_single_signal(strategy_name, signal, current_price)
            except Exception as e:
                self.logger.error(f"❌ Ошибка обработки сигнала {strategy_name}: {e}")
    
    def _process_single_signal(self, strategy_name: str, signal: Dict[str, Any], 
                             current_price: float) -> None:
        """Обработка одного торгового сигнала"""
        signal_type = signal['signal_type']
        api = self.strategy_apis[strategy_name]
        state = self.strategy_states[strategy_name]
        
        if signal_type in ['ENTER_LONG', 'ENTER_SHORT']:
            if state.in_position:
                self.logger.info(f"📊 {strategy_name}: уже в позиции")
                return
            
            # Определяем размер позиции
            balance = self._get_current_balance(api)
            risk_percent = signal.get('risk_percent', 0.01)
            trade_amount = balance * risk_percent
            
            # Открываем позицию
            order_response = self.position_service.open_position(
                api, signal, strategy_name, trade_amount, current_price, state
            )
            
            if order_response:
                # Регистрируем в риск-менеджере
                self.risk_manager.register_trade(strategy_name, signal, order_response)
                
                # Отправляем уведомление
                if self.notification_service:
                    self.notification_service.send_position_opened(
                        signal_type.replace('ENTER_', ''),
                        strategy_name,
                        signal.get('entry_price', current_price),
                        signal.get('stop_loss', 0),
                        signal.get('take_profit', 0),
                        trade_amount,
                        signal.get('signal_strength'),
                        signal.get('comment', '')
                    )
        
        elif signal_type in ['EXIT_LONG', 'EXIT_SHORT']:
            # Закрываем позицию
            close_response = self.position_service.close_position(
                api, state, strategy_name, signal_type, current_price
            )
            
            if close_response:
                # Обновляем риск-менеджер
                self.risk_manager.close_position(
                    strategy_name, "BTCUSDT", 
                    close_response['exit_price'], 
                    close_response['pnl']
                )
                
                # Отправляем уведомление
                if self.notification_service:
                    self.notification_service.send_position_closed(
                        strategy_name,
                        state.position_side,
                        close_response['exit_price'],
                        close_response['pnl'],
                        state.entry_price,
                        close_response['duration']
                    )
    
    def _process_neural_recommendations(self, market_data: Dict[str, Any], 
                                      strategy_signals: Dict[str, Any]) -> None:
        """Обработка рекомендаций нейронной сети"""
        try:
            neural_recommendation = self.neural_integration.make_neural_recommendation(
                market_data, strategy_signals
            )
            
            if neural_recommendation:
                self.logger.info(
                    f"🧠 Нейронная рекомендация: {neural_recommendation['strategy']} "
                    f"(уверенность: {neural_recommendation['confidence']:.1%})"
                )
                
                # Отправляем уведомление о рекомендации
                if self.notification_service:
                    self.notification_service.send_neural_recommendation(
                        neural_recommendation['strategy'],
                        neural_recommendation['confidence']
                    )
                
                # Размещаем ставку
                neural_bet = self.neural_integration.place_neural_bet(market_data, strategy_signals)
                if neural_bet:
                    self.logger.info(f"🎲 Нейронная ставка: {neural_bet['bet_id']}")
            
            # Очищаем старые ставки
            self.neural_integration.cleanup_old_bets()
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки нейронных рекомендаций: {e}")


def run_trading_bot_orchestrator(telegram_bot=None, shutdown_event=None):
    """
    🎼 НОВАЯ ФУНКЦИЯ ЗАПУСКА ТОРГОВОГО БОТА
    Использует сервисную архитектуру вместо монолитной функции
    
    Args:
        telegram_bot: Экземпляр Telegram бота
        shutdown_event: Событие для остановки
    """
    logger = get_secure_logger('bot_orchestrator')
    
    try:
        # Создаем shutdown_event если не передан
        if shutdown_event is None:
            shutdown_event = threading.Event()
        
        # Инициализируем нейронную интеграцию
        neural_integration = NeuralIntegration()
        
        # Создаем оркестратор
        orchestrator = TradingOrchestrator(
            telegram_bot=telegram_bot,
            neural_integration=neural_integration
        )
        
        # Инициализируем стратегии
        if not orchestrator.initialize_strategies():
            logger.error("❌ Не удалось инициализировать стратегии")
            return
        
        logger.info("🚀 Запуск торгового бота с новой архитектурой")
        
        # Запускаем торговый цикл
        orchestrator.run_trading_cycle(shutdown_event)
        
        logger.info("🛑 Торговый бот остановлен")
        
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
        if shutdown_event:
            shutdown_event.set()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка торгового бота: {e}")
        raise