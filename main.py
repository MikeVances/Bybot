# main.py
"""
Главный файл торгового бота с многопоточностью и централизованным риск-менеджментом
Версия 2.0 с интеграцией новой архитектуры стратегий

Функции: 
- Запуск торгового цикла с новыми стратегиями
- Telegram бот для управления
- Мониторинг рисков 
- Обработка сигналов завершения
- Менеджер стратегий
"""

import threading
import logging
import signal
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional

# Импорты основных компонентов бота
from bot.core import run_trading_with_risk_management
from bot.services.telegram_bot import TelegramBot
from bot.config_manager import config
from bot.risk import RiskManager
from bot.monitoring.metrics_exporter import MetricsExporter

# Импорты новой архитектуры стратегий
from bot.strategy.base import (
    BaseStrategy, 
    VolumeVWAPConfig,
    CumDeltaConfig,
    MultiTFConfig,
    get_version_info,
    validate_imports
)
from bot.strategy.implementations.volume_vwap_strategy import (
    VolumeVWAPStrategy,
    create_volume_vwap_strategy,
    create_conservative_volume_vwap,
    create_aggressive_volume_vwap
)
from bot.strategy.implementations.cumdelta_sr_strategy import (
    CumDeltaSRStrategy,
    create_cumdelta_sr_strategy,
    create_conservative_cumdelta_sr,
    create_aggressive_cumdelta_sr
)
from bot.strategy.implementations.multitf_volume_strategy import (
    MultiTFVolumeStrategy,
    create_multitf_volume_strategy,
    create_conservative_multitf_volume,
    create_aggressive_multitf_volume
)
from bot.strategy.implementations.fibonacci_rsi_strategy import (
    FibonacciRSIStrategy,
    create_fibonacci_rsi_strategy,
    create_conservative_fibonacci_rsi,
    create_aggressive_fibonacci_rsi
)

# Настройка логирования с улучшенным форматированием
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),  # Единый лог для всего бота
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Глобальные объекты для доступа из обработчиков сигналов
risk_manager = None
telegram_bot = None
metrics_exporter = None
strategy_manager = None
shutdown_event = threading.Event()


class StrategyManager:
    """
    Менеджер стратегий - управляет жизненным циклом торговых стратегий
    """
    
    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategies: List[str] = []
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
    def initialize_strategies(self) -> bool:
        """
        Инициализация всех доступных стратегий
        
        Returns:
            True если инициализация прошла успешно
        """
        try:
            self.logger.info("🔧 Инициализация стратегий...")
            
            # 1. Проверяем импорты базовой архитектуры
            import_status, import_message = validate_imports()
            if not import_status:
                self.logger.error(f"❌ Ошибка импортов: {import_message}")
                return False
            
            # 2. Логируем информацию о версии
            version_info = get_version_info()
            self.logger.info(f"📦 Базовая архитектура: v{version_info['version']}")
            
            # 3. Читаем список активных стратегий
            try:
                with open("bot/strategy/active_strategies.txt") as f:
                    configured_strategies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            except FileNotFoundError:
                configured_strategies = getattr(config, 'ACTIVE_STRATEGIES', ['volume_vwap_default'])
                self.logger.warning("⚠️ Файл active_strategies.txt не найден, используем fallback из config")

            self.logger.info(f"📋 Будут созданы только активные стратегии: {configured_strategies}")

            # 4. Создаем ТОЛЬКО активные стратегии
            for strategy_name in configured_strategies:
                try:
                    # Определяем factory функцию для каждой стратегии
                    if strategy_name == 'volume_vwap_default':
                        strategy_instance = create_volume_vwap_strategy()
                    elif strategy_name == 'volume_vwap_conservative':
                        strategy_instance = create_conservative_volume_vwap()
                    elif strategy_name == 'volume_vwap_aggressive':
                        strategy_instance = create_aggressive_volume_vwap()
                    elif strategy_name == 'cumdelta_sr_default':
                        strategy_instance = create_cumdelta_sr_strategy()
                    elif strategy_name == 'cumdelta_sr_conservative':
                        strategy_instance = create_conservative_cumdelta_sr()
                    elif strategy_name == 'cumdelta_sr_aggressive':
                        strategy_instance = create_aggressive_cumdelta_sr()
                    elif strategy_name == 'multitf_volume_default':
                        strategy_instance = create_multitf_volume_strategy()
                    elif strategy_name == 'multitf_volume_conservative':
                        strategy_instance = create_conservative_multitf_volume()
                    elif strategy_name == 'multitf_volume_aggressive':
                        strategy_instance = create_aggressive_multitf_volume()
                    elif strategy_name == 'fibonacci_rsi_default':
                        strategy_instance = create_fibonacci_rsi_strategy()
                    elif strategy_name == 'fibonacci_rsi_conservative':
                        strategy_instance = create_conservative_fibonacci_rsi()
                    elif strategy_name == 'fibonacci_rsi_aggressive':
                        strategy_instance = create_aggressive_fibonacci_rsi()
                    elif strategy_name == 'range_trading_default':
                        from bot.strategy.implementations.range_trading_strategy import create_range_trading_strategy
                        strategy_instance = create_range_trading_strategy()
                    else:
                        self.logger.warning(f"⚠️ Неизвестная стратегия '{strategy_name}', пропускаем")
                        continue

                    # Добавляем созданную стратегию
                    self.strategies[strategy_name] = strategy_instance
                    self.active_strategies.append(strategy_name)
                    self.logger.info(f"✅ Стратегия '{strategy_name}' создана и активирована")

                except Exception as e:
                    self.logger.error(f"❌ Ошибка создания стратегии '{strategy_name}': {e}")
            
            if not self.active_strategies:
                # Fallback - активируем стандартную стратегию
                if 'volume_vwap_default' in self.strategies:
                    self.active_strategies.append('volume_vwap_default')
                    self.logger.info("🔄 Активирована стандартная VolumeVWAP стратегия")
            
            self.logger.info(f"🚀 Инициализировано стратегий: {len(self.strategies)}")
            self.logger.info(f"🎯 Активных стратегий: {len(self.active_strategies)}")
            
            return len(self.active_strategies) > 0
            
        except Exception as e:
            self.logger.error(f"💥 Критическая ошибка инициализации стратегий: {e}")
            self.logger.error(traceback.format_exc())
            return False
    
    def get_active_strategies(self) -> List[BaseStrategy]:
        """Получение списка активных стратегий"""
        return [self.strategies[name] for name in self.active_strategies if name in self.strategies]
    
    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """Получение стратегии по имени"""
        return self.strategies.get(name)
    
    def get_strategy_info(self) -> Dict[str, any]:
        """Получение информации о стратегиях"""
        return {
            'total_strategies': len(self.strategies),
            'active_strategies': len(self.active_strategies),
            'strategy_names': list(self.strategies.keys()),
            'active_names': self.active_strategies
        }
    
    def activate_strategy(self, name: str) -> bool:
        """Активация стратегии"""
        if name in self.strategies and name not in self.active_strategies:
            self.active_strategies.append(name)
            self.logger.info(f"✅ Стратегия '{name}' активирована")
            return True
        return False
    
    def deactivate_strategy(self, name: str) -> bool:
        """Деактивация стратегии"""
        if name in self.active_strategies:
            self.active_strategies.remove(name)
            self.logger.info(f"❌ Стратегия '{name}' деактивирована")
            return True
        return False


def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown"""
    logger.info(f'Получен сигнал {signum}, начинаем graceful shutdown...')
    
    # Устанавливаем флаг завершения
    shutdown_event.set()
    
    # Экстренная остановка торговли
    if risk_manager:
        risk_manager.emergency_stop_all("Получен сигнал завершения")
    
    # Отправляем уведомление в Telegram
    if telegram_bot:
        try:
            telegram_bot.send_admin_message("🛑 Торговый бот получил сигнал завершения и останавливается...")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о завершении: {e}")
    
    # Даем время на завершение операций
    time.sleep(5)
    
    logger.info('Graceful shutdown завершен')
    sys.exit(0)


def setup_signal_handlers():
    """Настройка обработчиков сигналов"""
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Системный сигнал завершения
    if hasattr(signal, 'SIGHUP'):  # Unix-системы
        signal.signal(signal.SIGHUP, signal_handler)


def start_trading():
    """Запуск торгового потока с риск-менеджментом и новыми стратегиями"""
    logger.info('=== Торговый поток стартовал ===')
    
    try:
        # 1. Инициализируем риск-менеджер
        global risk_manager
        risk_config_path = getattr(config, 'RISK_CONFIG_PATH', None)
        risk_manager = RiskManager(risk_config_path)
        logger.info('✅ Риск-менеджер инициализирован')
        
        # 2. Инициализируем менеджер стратегий
        global strategy_manager
        strategy_manager = StrategyManager()
        
        if not strategy_manager.initialize_strategies():
            raise Exception("Не удалось инициализировать стратегии")
        
        logger.info('✅ Менеджер стратегий инициализирован')
        
        # 3. Отправляем стартовое уведомление
        if telegram_bot:
            try:
                risk_report = risk_manager.get_risk_report()
                strategy_info = strategy_manager.get_strategy_info()
                
                startup_message = f"""🚀 Торговый бот v2.0 запущен!
                
📊 Состояние системы:
• Лимит дневных сделок: {risk_report['limits']['max_daily_trades']}
• Максимум открытых позиций: {risk_report['limits']['max_open_positions']}
• Лимит дневных потерь: {risk_report['limits']['max_daily_loss_pct']}%

🎯 Стратегии:
• Всего стратегий: {strategy_info['total_strategies']}
• Активных стратегий: {strategy_info['active_strategies']}
• Активные: {', '.join(strategy_info['active_names'])}

⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔒 Риск-менеджмент: активен
🧠 Архитектура стратегий: v2.0"""
                
                telegram_bot.send_admin_message(startup_message, with_menu=True)
            except Exception as e:
                logger.error(f"Ошибка отправки стартового уведомления: {e}")
        
        # 4. Запускаем основной торговый цикл с новыми стратегиями
        run_trading_with_risk_management(
            risk_manager, 
            shutdown_event
        )
        
    except KeyboardInterrupt:
        logger.info('Торговый поток прерван пользователем')
    except Exception as e:
        logger.error(f'Торговый поток завершился с ошибкой: {e}', exc_info=True)
        
        # Отправляем уведомление об ошибке
        if telegram_bot:
            try:
                telegram_bot.send_admin_message(f"❌ КРИТИЧЕСКАЯ ОШИБКА в торговом потоке:\n{str(e)}")
            except Exception:
                pass
    finally:
        logger.info('=== Торговый поток завершён ===')
        
        # Финальный отчет
        if risk_manager:
            try:
                final_report = risk_manager.get_risk_report()
                strategy_info = strategy_manager.get_strategy_info() if strategy_manager else {}
                
                logger.info(f"Финальная статистика: {final_report['daily_trades']} сделок, "
                           f"P&L: ${final_report['daily_pnl']:.2f}")
                
                if telegram_bot:
                    shutdown_message = f"""⛔ Торговый бот v2.0 остановлен
                    
📈 Итоги сессии:
• Сделок за день: {final_report['daily_trades']}
• P&L за день: ${final_report['daily_pnl']:.2f}
• Открытых позиций: {final_report['open_positions_count']}
• Заблокированных стратегий: {len(final_report['blocked_strategies'])}

🎯 Стратегии:
• Использовалось стратегий: {strategy_info.get('active_strategies', 0)}

⏰ Время остановки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                    
                    telegram_bot.send_admin_message(shutdown_message)
            except Exception as e:
                logger.error(f"Ошибка формирования финального отчета: {e}")


def start_telegram():
    """Запуск Telegram бота (заглушка - бот запускается по требованию)"""
    logger.info('=== Telegram бот готов к работе ===')
    
    try:
        if telegram_bot:
            logger.info('Telegram бот инициализирован и готов к командам')
        else:
            logger.warning('Telegram бот не инициализирован')
        
    except Exception as e:
        logger.error(f'Ошибка инициализации Telegram бота: {e}', exc_info=True)


def start_metrics_monitoring():
    """Запуск мониторинга метрик с поддержкой стратегий"""
    logger.info('=== Поток мониторинга метрик стартовал ===')
    
    try:
        global metrics_exporter
        metrics_exporter = MetricsExporter(
            risk_manager=risk_manager,
            strategy_manager=strategy_manager,  # Добавляем менеджер стратегий
            port=getattr(config, 'METRICS_PORT', 8000)
        )
        
        metrics_exporter.start(shutdown_event)
        
    except Exception as e:
        logger.error(f'Поток мониторинга метрик завершился с ошибкой: {e}', exc_info=True)
    finally:
        logger.info('=== Поток мониторинга метрик завершён ===')


def start_risk_monitoring():
    """Запуск мониторинга рисков (отдельный поток)"""
    logger.info('=== Поток мониторинга рисков стартовал ===')
    
    try:
        while not shutdown_event.is_set():
            if risk_manager and strategy_manager:
                # Очищаем старые данные каждый час
                risk_manager.cleanup_old_data()
                
                # Проверяем критические события
                risk_report = risk_manager.get_risk_report()
                strategy_info = strategy_manager.get_strategy_info()
                
                # Проверяем аварийные ситуации
                if risk_report['daily_pnl'] < -1000:  # Потери больше $1000
                    risk_manager.emergency_stop_all("Критические дневные потери")
                    
                    if telegram_bot:
                        telegram_bot.send_admin_message(
                            f"🚨 АВАРИЙНАЯ ОСТАНОВКА!\nДневные потери: ${risk_report['daily_pnl']:.2f}"
                        )
                
                # Отправляем периодические отчеты (каждые 4 часа)
                current_hour = datetime.now().hour
                if current_hour % 4 == 0 and datetime.now().minute < 5:
                    if telegram_bot and risk_report['open_positions_count'] > 0:
                        report_message = f"""📊 Периодический отчет о рисках:
                        
🔢 Статистика:
• Открытых позиций: {risk_report['open_positions_count']}
• Дневных сделок: {risk_report['daily_trades']}
• Дневный P&L: ${risk_report['daily_pnl']:.2f}
• Общая экспозиция: ${risk_report['total_exposure']:.2f}

🎯 Стратегии:
• Активных стратегий: {strategy_info['active_strategies']}
• Заблокированных стратегий: {len(risk_report['blocked_strategies'])}

⚠️ Статус:
• Аварийный стоп: {'Да' if risk_report['emergency_stop'] else 'Нет'}"""
                        
                        telegram_bot.send_admin_message(report_message)
                        time.sleep(300)  # Защита от спама
            
            # Проверяем каждые 5 минут
            shutdown_event.wait(300)
            
    except Exception as e:
        logger.error(f'Поток мониторинга рисков завершился с ошибкой: {e}', exc_info=True)
    finally:
        logger.info('=== Поток мониторинга рисков завершён ===')


def health_check():
    """Проверка здоровья системы"""
    try:
        checks = {
            'risk_manager': risk_manager is not None,
            'strategy_manager': strategy_manager is not None,
            'telegram_bot': telegram_bot is not None,
            'emergency_stop': risk_manager.emergency_stop if risk_manager else False,
            'blocked_strategies': len(risk_manager.blocked_strategies) if risk_manager else 0,
            'active_strategies': len(strategy_manager.active_strategies) if strategy_manager else 0
        }
        
        logger.debug(f"Health check: {checks}")
        
        # Система здорова если:
        # - Есть риск-менеджер и менеджер стратегий
        # - Нет аварийного стопа
        # - Есть активные стратегии
        return all([
            checks['risk_manager'], 
            checks['strategy_manager'],
            not checks['emergency_stop'],
            checks['active_strategies'] > 0
        ])
        
    except Exception as e:
        logger.error(f"Ошибка health check: {e}")
        return False


def run_strategy_tests():
    """Запуск тестов стратегий при старте"""
    logger.info("🧪 Запуск тестов стратегий...")
    
    try:
        # Импортируем и запускаем тесты
        from test_volume_vwap_strategy import run_comprehensive_test
        
        test_results = run_comprehensive_test()
        
        if all(test_results.values()):
            logger.info("✅ Все тесты стратегий пройдены")
            return True
        else:
            failed_tests = [test for test, result in test_results.items() if not result]
            logger.warning(f"⚠️ Провалены тесты: {failed_tests}")
            return False
            
    except ImportError:
        logger.warning("⚠️ Тесты стратегий не найдены, пропускаем")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка запуска тестов: {e}")
        return False


def main():
    """Главная функция"""
    logger.info('='*60)
    logger.info('🚀 ЗАПУСК ТОРГОВОГО БОТА v2.0 С НОВОЙ АРХИТЕКТУРОЙ СТРАТЕГИЙ')
    logger.info('='*60)

    # 🔒 Проверяем единственность экземпляра
    try:
        from bot.core.singleton import ensure_single_instance
        if not ensure_single_instance("trading_bot_main"):
            logger.error("❌ Торговый бот уже запущен!")
            logger.error("   Для принудительной остановки используйте: python -c 'from bot.core.singleton import kill_existing_bots; kill_existing_bots()'")
            return
        logger.info("✅ Singleton проверка пройдена")
    except ImportError as e:
        logger.warning(f"⚠️  Singleton система недоступна: {e}")

    # Настраиваем обработчики сигналов
    setup_signal_handlers()
    
    # Опционально запускаем тесты при старте
    if getattr(config, 'RUN_TESTS_ON_STARTUP', False):
        if not run_strategy_tests():
            logger.error("❌ Тесты стратегий провалены, остановка")
            return
    
    threads = []
    
    try:
        # 1. Инициализируем Telegram бота ПЕРЕД торговым потоком (если включен)
        logger.info(f'🔍 Проверяем TELEGRAM_ENABLED: {getattr(config, "TELEGRAM_ENABLED", False)}')
        if getattr(config, 'TELEGRAM_ENABLED', False):
            logger.info('📱 TELEGRAM_ENABLED=True, инициализируем бота...')
            try:
                global telegram_bot
                telegram_bot = TelegramBot(token=config.TELEGRAM_TOKEN)
                logger.info('✅ Telegram бот инициализирован')
                
                # Запускаем Telegram бота используя стандартный метод start()
                telegram_bot.start()
                logger.info('✅ Telegram бот запущен')
                
                # Даем время Telegram боту запуститься
                time.sleep(3)
            except Exception as e:
                logger.error(f'❌ Ошибка инициализации Telegram бота: {e}')
                telegram_bot = None
        else:
            logger.info('📱 TELEGRAM_ENABLED=False, пропускаем инициализацию')
        
        # 2. Запускаем торговый поток (основной) в отдельном процессе
        trading_thread = threading.Thread(
            target=start_trading, 
            name="TradingThread",
            daemon=True  # Делаем daemon, чтобы не блокировать
        )
        threads.append(trading_thread)
        trading_thread.start()
        logger.info('✅ Торговый поток запущен')
        
        # 3. Запускаем мониторинг рисков
        risk_monitoring_thread = threading.Thread(
            target=start_risk_monitoring,
            name="RiskMonitoringThread", 
            daemon=True
        )
        threads.append(risk_monitoring_thread)
        risk_monitoring_thread.start()
        logger.info('✅ Мониторинг рисков запущен')
        
        # 4. Запускаем экспорт метрик (если включен)
        if getattr(config, 'METRICS_ENABLED', False):
            metrics_thread = threading.Thread(
                target=start_metrics_monitoring,
                name="MetricsThread",
                daemon=True
            )
            threads.append(metrics_thread)
            metrics_thread.start()
            logger.info('✅ Экспорт метрик запущен')
        
        logger.info(f'🎯 Главный процесс: все {len(threads)} потоков запущены')
        
        # Основной цикл мониторинга
        # Даем системе время на полную инициализацию
        time.sleep(10)

        while not shutdown_event.is_set():
            # Проверяем здоровье системы каждые 30 секунд, но только после инициализации
            try:
                if not health_check():
                    logger.debug("⚠️ Система еще инициализируется или найдены проблемы")
            except Exception as e:
                logger.debug(f"Health check error: {e}")
            
            # Проверяем живость потоков
            for thread in threads:
                if not thread.is_alive() and thread.name == "TradingThread":
                    logger.error(f"💀 Критический поток {thread.name} завершился!")
                    shutdown_event.set()
                    break
            
            time.sleep(30)
        
        # Ждем завершения всех потоков
        logger.info('⏳ Ожидание завершения всех потоков...')
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=10)  # Даем 10 секунд на завершение
                
    except KeyboardInterrupt:
        logger.info('❌ Получен сигнал прерывания от пользователя')
        shutdown_event.set()
    except Exception as e:
        logger.error(f'💥 Критическая ошибка в главном процессе: {e}', exc_info=True)
        shutdown_event.set()
    finally:
        logger.info('🏁 Главный процесс завершён: все потоки остановлены')
        logger.info('='*60)


# Запускаем main() всегда, независимо от того, как импортирован модуль
if __name__ == "__main__":
    main()
else:
    # Если импортирован как модуль, все равно запускаем
    main()