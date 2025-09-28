# bot/core/trader.py
# Основной торговый цикл с интегрированным риск-менеджментом и нейронной сетью
# Функции: выполнение стратегий, контроль рисков, управление позициями, мониторинг

import time as time_module
import csv
import uuid
import logging
from datetime import datetime, timezone, timedelta
import importlib
import os
import tempfile
import pandas as pd
import threading
from typing import Optional, Dict, Any

from bot.exchange.api_adapter import create_trading_bot_adapter
from bot.ai import NeuralIntegration
from bot.risk import RiskManager
from config import get_strategy_config, USE_V5_API, USE_TESTNET, SYMBOL

# 🛡️ КРИТИЧЕСКИЕ ИМПОРТЫ БЕЗОПАСНОСТИ
from bot.core.order_manager import get_order_manager, OrderRequest
from bot.core.thread_safe_state import get_bot_state
from bot.core.rate_limiter import get_rate_limiter
from bot.core.secure_logger import get_secure_logger
from bot.core.error_handler import get_error_handler, handle_trading_error, ErrorContext, RecoveryStrategy
from bot.core.emergency_stop import global_emergency_stop
from bot.core.global_circuit_breaker import global_circuit_breaker
from bot.core.exceptions import OrderRejectionError, RateLimitError, EmergencyStopError
from bot.core.enhanced_api_connection import (
    get_enhanced_connection_manager,
    ConnectionState,
)
from bot.core.blocking_alerts import report_order_block

# Импорты основных компонентов бота
from bot.risk import RiskManager
from bot.monitoring.metrics_exporter import MetricsExporter

def send_position_notification(telegram_bot, signal_type: str, strategy_name: str, 
                             entry_price: float, stop_loss: float, take_profit: float, 
                             trade_amount: float, signal_strength: float = None, comment: str = ""):
    """
    Отправка уведомления о позиции через Telegram
    
    Args:
        telegram_bot: Экземпляр Telegram бота
        signal_type: Тип сигнала (BUY/SELL)
        strategy_name: Название стратегии
        entry_price: Цена входа
        stop_loss: Стоп-лосс
        take_profit: Тейк-профит
        trade_amount: Размер позиции
        signal_strength: Сила сигнала (опционально)
        comment: Дополнительный комментарий
    """
    try:
        # Формируем сообщение
        emoji = "🟢" if signal_type == "BUY" else "🔴"
        side_text = "LONG" if signal_type == "BUY" else "SHORT"
        
        message = f"""
{emoji} НОВАЯ ПОЗИЦИЯ ОТКРЫТА

📊 Стратегия: {strategy_name}
🎯 Сторона: {side_text} ({signal_type})
💰 Цена входа: ${entry_price:,.2f}
📈 Размер: {trade_amount} BTC

🛡️ Стоп-лосс: ${stop_loss:,.2f}
🎯 Тейк-профит: ${take_profit:,.2f}

📊 Risk/Reward: {((take_profit - entry_price) / (entry_price - stop_loss)):.2f}
"""
        
        if signal_strength:
            message += f"💪 Сила сигнала: {signal_strength:.2f}\n"
        
        if comment:
            message += f"💬 Комментарий: {comment}\n"
        
        message += f"\n⏰ **Время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Отправляем уведомление
        telegram_bot.send_admin_message(message)
        
    except Exception as e:
        print(f"[ERROR] Ошибка отправки уведомления о позиции: {e}")

def send_position_close_notification(telegram_bot, strategy_name: str, 
                                  side: str, exit_price: float, pnl: float, 
                                  entry_price: float = None, duration: str = None):
    """
    Отправка уведомления о закрытии позиции
    
    Args:
        telegram_bot: Экземпляр Telegram бота
        strategy_name: Название стратегии
        side: Сторона позиции (BUY/SELL)
        exit_price: Цена выхода
        pnl: Прибыль/убыток
        entry_price: Цена входа (опционально)
        duration: Длительность позиции (опционально)
    """
    try:
        # Определяем эмодзи и цвет
        if pnl > 0:
            emoji = "✅"
            result_text = "ПРИБЫЛЬ"
        elif pnl < 0:
            emoji = "❌"
            result_text = "УБЫТОК"
        else:
            emoji = "⚪"
            result_text = "БЕЗУБЫТОЧНО"
        
        side_text = "LONG" if side == "BUY" else "SHORT"
        
        message = f"""
{emoji} ПОЗИЦИЯ ЗАКРЫТА

📊 Стратегия: {strategy_name}
🎯 Сторона: {side_text} ({side})
💰 Цена выхода: ${exit_price:,.2f}
"""
        
        if entry_price:
            message += f"📈 Цена входа: ${entry_price:,.2f}\n"
        
        message += f"""
💵 P&L: ${pnl:,.2f} ({result_text})
"""
        
        if duration:
            message += f"⏱️ Длительность: {duration}\n"
        
        message += f"\n⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Отправляем уведомление
        telegram_bot.send_admin_message(message)
        
    except Exception as e:
        print(f"[ERROR] Ошибка отправки уведомления о закрытии позиции: {e}")

def load_strategy(strategy_name):
    """Загрузка стратегии по имени с обработкой ошибок"""
    try:
        # Сначала пробуем загрузить новую архитектуру стратегий
        if strategy_name.startswith('volume_vwap'):
            # Загружаем VolumeVWAP стратегию из новой архитектуры
            from bot.strategy.implementations.volume_vwap_strategy_v3 import create_volume_vwap_strategy
            logging.info(f"✅ Стратегия {strategy_name} загружена из новой архитектуры")
            return create_volume_vwap_strategy
        elif strategy_name.startswith('cumdelta'):
            # Загружаем CumDelta стратегию из новой архитектуры
            from bot.strategy.implementations.cumdelta_sr_strategy_v3 import create_cumdelta_sr_strategy
            logging.info(f"✅ Стратегия {strategy_name} загружена из новой архитектуры")
            return create_cumdelta_sr_strategy
        elif strategy_name.startswith('multitf'):
            # Загружаем MultiTF стратегию из новой архитектуры
            from bot.strategy.implementations.multitf_volume_strategy_v3 import create_multitf_volume_strategy
            logging.info(f"✅ Стратегия {strategy_name} загружена из новой архитектуры")
            return create_multitf_volume_strategy
        elif strategy_name.startswith('fibonacci'):
            # Загружаем Fibonacci RSI стратегию из новой архитектуры
            from bot.strategy.implementations.fibonacci_rsi_strategy_v3 import create_fibonacci_rsi_strategy
            logging.info(f"✅ Стратегия {strategy_name} загружена из новой архитектуры")
            return create_fibonacci_rsi_strategy
        elif strategy_name.startswith('range_trading'):
            # Загружаем Range Trading стратегию из новой архитектуры
            from bot.strategy.implementations.range_trading_strategy_v3 import create_range_trading_strategy
            logging.info(f"✅ Стратегия {strategy_name} загружена из новой архитектуры")
            return create_range_trading_strategy
        else:
            # Пробуем загрузить старую архитектуру
            module = importlib.import_module(f"bot.strategy.{strategy_name}")
            class_name = "".join([part.capitalize() for part in strategy_name.split('_')])
            strategy_class = getattr(module, class_name)
            logging.info(f"✅ Стратегия {strategy_name} загружена из старой архитектуры")
            return strategy_class
    except ImportError as e:
        logging.error(f"❌ Модуль стратегии {strategy_name} не найден: {e}")
        return None
    except AttributeError as e:
        logging.error(f"❌ Класс стратегии {strategy_name} не найден: {e}")
        return None
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки стратегии {strategy_name}: {e}")
        return None

def get_active_strategies():
    """Получение списка активных стратегий из файла"""
    try:
        with open("bot/strategy/active_strategies.txt") as f:
            strategies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        logging.info(f"📋 Загружено {len(strategies)} активных стратегий: {strategies}")
        return strategies
    except FileNotFoundError:
        logging.warning("⚠️ Файл active_strategies.txt не найден, используем новую VolumeVWAP стратегию")
        return ["volume_vwap_default"]
    except Exception as e:
        logging.error(f"❌ Ошибка чтения файла активных стратегий: {e}")
        return ["volume_vwap_default"]

class BotState:
    """Расширенное состояние бота для отслеживания позиций"""
    def __init__(self):
        self.in_position = False
        self.position_side = None
        self.entry_price = None
        self.entry_time = None
        self.stop_loss = None
        self.take_profit = None
        self.position_size = 0.0
        self.unrealized_pnl = 0.0
        self.last_update = None

    def update_position(self, current_price: float):
        """Обновление P&L позиции"""
        if self.in_position and self.entry_price:
            if self.position_side == 'BUY':
                self.unrealized_pnl = (current_price - self.entry_price) * self.position_size
            elif self.position_side == 'SELL':
                self.unrealized_pnl = (self.entry_price - current_price) * self.position_size
            self.last_update = datetime.now()

    def reset(self):
        """Сброс состояния позиции"""
        self.in_position = False
        self.position_side = None
        self.entry_price = None
        self.entry_time = None
        self.stop_loss = None
        self.take_profit = None
        self.position_size = 0.0
        self.unrealized_pnl = 0.0
        self.last_update = None

def setup_strategy_logger(strategy_name):
    """Настройка отдельного логгера для каждой стратегии"""
    os.makedirs('data/logs/strategies', exist_ok=True)
    
    logger = logging.getLogger(f'strategy_{strategy_name}')
    
    # Избегаем дублирования обработчиков
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Файловый обработчик
        file_handler = logging.FileHandler(f'data/logs/strategies/{strategy_name}.log')
        file_handler.setLevel(logging.INFO)
        
        # Форматтер
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
    
    return logger

def log_trade_journal(strategy_name, signal, all_market_data):
    """Расширенное логирование сигналов в журнал сделок"""
    filename = "data/trade_journal.csv"
    signals_log_file = "data/signals_log.csv"
    os.makedirs("data", exist_ok=True)

    fieldnames = [
        'timestamp', 'signal_id', 'strategy', 'signal', 'entry_price', 'stop_loss', 'take_profit', 'comment',
        'tf', 'open', 'high', 'low', 'close', 'volume', 'signal_strength', 'risk_reward_ratio'
    ]

    signal_log_fields = [
        'timestamp', 'signal_id', 'strategy', 'signal', 'entry_price', 'stop_loss', 'take_profit',
        'comment', 'signal_strength', 'risk_reward_ratio', 'confluence_factors'
    ]

    _ensure_trade_journal_schema(filename, fieldnames)
    _ensure_csv_header(signals_log_file, signal_log_fields)

    current_timestamp = datetime.now(timezone.utc).isoformat()
    signal_id = signal.get('signal_id')
    if not signal_id:
        signal_id = f"sig_{uuid.uuid4()}"
        signal['signal_id'] = signal_id

    # Логируем агрегированную информацию по сигналу (1 строка на событие)
    aggregated_row = {
        'timestamp': current_timestamp,
        'signal_id': signal_id,
        'strategy': strategy_name,
        'signal': signal.get('signal', ''),
        'entry_price': signal.get('entry_price', ''),
        'stop_loss': signal.get('stop_loss', ''),
        'take_profit': signal.get('take_profit', ''),
        'comment': signal.get('comment', ''),
        'signal_strength': signal.get('signal_strength', 0),
        'risk_reward_ratio': signal.get('risk_reward_ratio', 0),
        'confluence_factors': ','.join(signal.get('confluence_factors', [])) if signal.get('confluence_factors') else ''
    }

    with open(signals_log_file, 'a', newline='') as sig_file:
        sig_writer = csv.DictWriter(sig_file, fieldnames=signal_log_fields)
        if sig_file.tell() == 0:
            sig_writer.writeheader()
        sig_writer.writerow(aggregated_row)

    _persist_market_snapshots(all_market_data, signal_id, current_timestamp)

    # Для каждого таймфрейма логируем последнюю свечу
    for tf, df in all_market_data.items():
        if df is None or len(df) == 0:
            continue
            
        try:
            last = df.iloc[-1]
            
            # Расчет дополнительных метрик
            signal_strength = signal.get('signal_strength', 0)
            risk_reward_ratio = signal.get('risk_reward_ratio', 0)
            
            row = {
                'timestamp': current_timestamp,
                'signal_id': signal_id,
                'strategy': strategy_name,
                'signal': signal.get('signal', ''),
                'entry_price': signal.get('entry_price', ''),
                'stop_loss': signal.get('stop_loss', ''),
                'take_profit': signal.get('take_profit', ''),
                'comment': signal.get('comment', ''),
                'tf': tf,
                'open': last['open'],
                'high': last['high'],
                'low': last['low'],
                'close': last['close'],
                'volume': last['volume'],
                'signal_strength': signal_strength,
                'risk_reward_ratio': risk_reward_ratio
            }
            
            with open(filename, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(row)

        except Exception as e:
            logging.error(f"❌ Ошибка записи журнала для {tf}: {e}")


def _persist_market_snapshots(all_market_data, signal_id: str, timestamp: str) -> None:
    """Сохраняет снимки рыночных данных по всем таймфреймам на момент сигнала."""

    try:
        snapshot_root = os.path.join('data', 'snapshots', timestamp[:10])
        os.makedirs(snapshot_root, exist_ok=True)
        for tf, df in all_market_data.items():
            if df is None or df.empty:
                continue

            tf_safe = str(tf).replace('/', '_')
            snapshot_path = os.path.join(snapshot_root, f"{signal_id}_{tf_safe}.csv")
            try:
                df_to_save = df.copy()
                df_to_save.to_csv(snapshot_path, index=True, index_label='timestamp')
            except Exception as inner_exc:
                logging.error(f"❌ Не удалось сохранить snapshot для {tf}: {inner_exc}")
    except Exception as exc:
        logging.error(f"❌ Ошибка сохранения snapshots: {exc}")


def _ensure_csv_header(path: str, fieldnames: list[str]) -> None:
    """Создаёт CSV с нужным заголовком, если файл отсутствует."""

    if not os.path.exists(path):
        with open(path, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()


def _ensure_trade_journal_schema(path: str, fieldnames: list[str]) -> None:
    """Мигрирует существующий trade_journal.csv к новой схеме с signal_id."""

    if not os.path.exists(path):
        _ensure_csv_header(path, fieldnames)
        return

    with open(path, newline='', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        try:
            existing_header = next(reader)
        except StopIteration:
            existing_header = []
        rows = list(reader)

    if existing_header == fieldnames:
        return

    tmp_fd, tmp_path = tempfile.mkstemp(prefix='trade_journal_', suffix='.csv')
    os.close(tmp_fd)

    try:
        with open(tmp_path, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            for row in rows:
                mapping: Dict[str, Any] = {key: '' for key in fieldnames}

                for idx, value in enumerate(row):
                    if idx < len(existing_header):
                        key = existing_header[idx]
                        if key in mapping:
                            mapping[key] = value

                if 'signal_id' not in existing_header:
                    mapping['signal_id'] = f"legacy_{uuid.uuid4()}"

                writer.writerow(mapping)

        os.replace(tmp_path, path)
        logging.info("🔄 trade_journal.csv мигрирован под новую схему (%s)", ','.join(fieldnames))
    except Exception as exc:
        logging.error(f"❌ Ошибка миграции trade_journal: {exc}")
        try:
            os.remove(tmp_path)
        except Exception:
            pass

def get_current_balance(api):
    """Получение текущего баланса с обработкой ошибок"""
    try:
        balance_data = api.get_wallet_balance_v5()
        logging.debug(f"💾 Balance API response: retCode={balance_data.get('retCode') if balance_data else 'None'}")

        if balance_data and balance_data.get('retCode') == 0:
            coins = balance_data['result']['list'][0]['coin']
            logging.debug(f"💰 Found {len(coins)} coins in balance")

            usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
            if usdt:
                balance = float(usdt['walletBalance'])
                logging.debug(f"💵 USDT balance found: ${balance:.2f}")
                return balance
            else:
                logging.warning("⚠️ USDT не найден в балансе")
        else:
            logging.error(f"❌ Неверный ответ API: {balance_data}")
    except Exception as e:
        logging.error(f"❌ Ошибка получения баланса: {e}")
        import traceback
        logging.error(f"📄 Traceback: {traceback.format_exc()}")

    logging.warning("💸 Возвращаем баланс 0.0")
    return 0.0

def get_current_price(all_market_data):
    """Получение текущей цены из рыночных данных"""
    try:
        for tf in ['1m', '5m', '15m', '1h']:
            if tf in all_market_data and all_market_data[tf] is not None and not all_market_data[tf].empty:
                return float(all_market_data[tf].iloc[-1]['close'])
    except Exception as e:
        logging.error(f"❌ Ошибка получения текущей цены: {e}")
    return 0.0

def update_position_in_risk_manager(risk_manager: RiskManager, strategy_name: str, 
                                  symbol: str, current_price: float, current_balance: float):
    """Обновление позиций в риск-менеджере"""
    try:
        risk_manager.update_position(strategy_name, symbol, current_price, current_balance)
    except Exception as e:
        logging.error(f"❌ Ошибка обновления позиции в риск-менеджере: {e}")

def sync_position_with_exchange(api, state: BotState, symbol: str = None):
    """Синхронизация состояния позиции с биржей"""
    if symbol is None:
        symbol = SYMBOL
    try:
        positions = api.get_positions(symbol)
        if positions and positions.get('retCode') == 0:
            position_list = positions['result']['list']
            
            # Ищем открытую позицию
            open_position = None
            for pos in position_list:
                if float(pos.get('size', 0)) > 0:
                    open_position = pos
                    break
            
            if open_position:
                # Обновляем состояние на основе данных биржи
                state.in_position = True
                state.position_side = open_position['side']
                state.entry_price = float(open_position['avgPrice'])
                state.position_size = float(open_position['size'])
                state.unrealized_pnl = float(open_position['unrealisedPnl'])
                
                logging.info(f"📊 Синхронизация позиции: {state.position_side} {state.position_size} по ${state.entry_price}")
            else:
                # Нет открытых позиций
                if state.in_position:
                    logging.info("🔄 Позиция закрыта на бирже, обновляем состояние")
                    state.reset()
        
    except Exception as e:
        logging.error(f"❌ Ошибка синхронизации с биржей: {e}")

def run_trading_with_risk_management(
    risk_manager: RiskManager,
    shutdown_event: threading.Event,
    *,
    telegram_bot: Optional[Any] = None,
):
    """Основной торговый цикл с полным риск-менеджментом"""
    
    # Настройка логирования
    main_logger = logging.getLogger('main_trading')
    main_logger.setLevel(logging.INFO)

    # === БЛОК А2: TTL КЭШИРОВАНИЕ ДЛЯ ПРЕДОТВРАЩЕНИЯ MEMORY LEAKS ===
    from bot.strategy.utils.indicators import TTLCache

    # Кэши с автоматической очисткой для предотвращения утечек памяти
    market_data_cache = TTLCache(maxsize=10, ttl=300)  # 5 минут
    strategy_results_cache = TTLCache(maxsize=50, ttl=180)  # 3 минуты
    balance_cache = TTLCache(maxsize=20, ttl=60)  # 1 минута
    position_cache = TTLCache(maxsize=20, ttl=120)  # 2 минуты

    main_logger.info("🗂️ TTL кэширование инициализировано для предотвращения memory leaks")
    
    try:
        if telegram_bot:
            try:
                from bot.services.notification_service import get_notification_service
                get_notification_service(telegram_bot)
            except Exception as e:
                main_logger.warning(f"⚠️ Не удалось инициализировать сервис уведомлений: {e}")

            try:
                from bot.core.blocking_alerts import get_blocking_alerts_manager
                get_blocking_alerts_manager(telegram_bot)
            except Exception as e:
                main_logger.warning(f"⚠️ Не удалось связать Telegram бот с системой блокировок: {e}")
        else:
            main_logger.info("📱 Telegram бот не предоставлен — уведомления отключены для текущего запуска")

        # Инициализируем нейронную интеграцию
        neural_integration = NeuralIntegration()
        neural_integration.load_state()
        main_logger.info("🧠 Нейронная интеграция инициализирована")
        
        # Создаем отдельные API клиенты для каждой стратегии
        strategy_apis = {}
        strategy_states = {}
        strategy_loggers = {}
        strategy_configs = {}
        
        strategy_names = get_active_strategies()
        main_logger.info(f"📋 Найдено {len(strategy_names)} активных стратегий")

        # Подготавливаем конфигурации
        for strategy_name in strategy_names:
            try:
                strategy_configs[strategy_name] = get_strategy_config(strategy_name)
            except Exception as cfg_error:
                main_logger.error(f"❌ Ошибка чтения конфигурации {strategy_name}: {cfg_error}")

        # 🚨 ИНИЦИАЛИЗАЦИЯ EMERGENCY STOP СИСТЕМЫ
        main_logger.info("🚨 Инициализация системы экстренной остановки...")

        for strategy_name, config in strategy_configs.items():
            try:
                if not config.get('enabled', True):
                    main_logger.info(f"⏸️ Стратегия {strategy_name} отключена в конфигурации")
                    continue

                adapter = create_trading_bot_adapter(
                    symbol=SYMBOL,
                    api_key=config['api_key'],
                    api_secret=config['api_secret'],
                    uid=config.get('uid'),
                    testnet=USE_TESTNET
                )
                strategy_apis[strategy_name] = adapter
                main_logger.info(f"✅ API клиент подготовлен для {strategy_name}")
            except Exception as api_error:
                main_logger.error(f"❌ Ошибка создания API для {strategy_name}: {api_error}")

        # Запускаем мониторинг emergency stop
        if strategy_apis:
            global_emergency_stop.start_monitoring(strategy_apis)
            main_logger.info("🚨 Система экстренной остановки запущена")
        else:
            main_logger.error("❌ Не удалось подготовить API клиенты для стратегий")
            return

        # 🔌 ЗАПУСК CIRCUIT BREAKER
        global_circuit_breaker.start_monitoring()
        main_logger.info("🔌 Circuit Breaker запущен")
        
        # Инициализация стратегий
        for strategy_name, adapter in strategy_apis.items():
            try:
                config = strategy_configs[strategy_name]
                strategy_states[strategy_name] = BotState()
                strategy_loggers[strategy_name] = setup_strategy_logger(strategy_name)
                
                main_logger.info(f"✅ Инициализирована стратегия {strategy_name}: {config['description']}")
                
            except Exception as e:
                main_logger.error(f"❌ Ошибка инициализации стратегии {strategy_name}: {e}")
                continue
        
        if not strategy_apis:
            main_logger.error("❌ Нет доступных стратегий для торговли!")
            return
        
        main_logger.info(f"🚀 Торговый бот запущен с риск-менеджментом и {len(strategy_apis)} стратегиями")
        
        # Основной торговый цикл
        iteration_count = 0
        last_sync_time = datetime.now()
        last_connection_state = None
        last_connection_alert_at = datetime.min
        
        while not shutdown_event.is_set():
            try:
                iteration_count += 1
                current_time = datetime.now()
                
                main_logger.info(f"🔄 Итерация #{iteration_count} - {current_time.strftime('%H:%M:%S')}")
                
                # Проверяем состояние API подключения
                connection_manager = get_enhanced_connection_manager()
                if connection_manager:
                    health = connection_manager.get_connection_health()
                    connection_state = health.get('state', ConnectionState.HEALTHY.value)

                    if connection_state != last_connection_state:
                        if last_connection_state is not None:
                            main_logger.info(
                                "🌐 Состояние API: %s → %s",
                                last_connection_state,
                                connection_state,
                            )
                        else:
                            main_logger.info("🌐 Состояние API: %s", connection_state)
                        last_connection_state = connection_state
                        if connection_state == ConnectionState.HEALTHY.value:
                            last_connection_alert_at = datetime.min

                    degraded_states = {
                        ConnectionState.DEGRADED.value,
                        ConnectionState.UNSTABLE.value,
                        ConnectionState.FAILED.value,
                    }
                    if connection_state in degraded_states:
                        now_ts = datetime.now()
                        time_since_alert = (now_ts - last_connection_alert_at) if last_connection_alert_at != datetime.min else timedelta.max

                        # Формируем подробности для алерта
                        alert_details = {
                            'state': connection_state,
                            'endpoint': health.get('current_endpoint'),
                            'response_time': round(health.get('endpoint_response_time') or 0.0, 4),
                            'consecutive_failures': health.get('consecutive_failures'),
                        }

                        if connection_state == ConnectionState.DEGRADED.value:
                            if time_since_alert.total_seconds() >= 120:
                                report_order_block(
                                    reason='api_performance',
                                    symbol='ALL',
                                    strategy='SYSTEM',
                                    message='API подключение в состоянии DEGRADED — продолжение торговли с повышенной осторожностью',
                                    details=alert_details,
                                )
                                last_connection_alert_at = now_ts
                                main_logger.warning(
                                    "⚠️ API подключение DEGRADED (response %.3fs, %s неудачных подряд)",
                                    alert_details['response_time'],
                                    alert_details['consecutive_failures'],
                                )
                        else:
                            wait_seconds = 60 if connection_state == ConnectionState.FAILED.value else 30
                            severity_log = main_logger.critical if connection_state == ConnectionState.FAILED.value else main_logger.warning
                            if time_since_alert.total_seconds() >= 30:
                                report_order_block(
                                    reason='api_performance',
                                    symbol='ALL',
                                    strategy='SYSTEM',
                                    message=f'API подключение нестабильно ({connection_state}). Торговый цикл поставлен на паузу',
                                    details=alert_details,
                                )
                                last_connection_alert_at = now_ts
                            severity_log(
                                "🚦 API состояние %s — пауза %s сек (response %.3fs)",
                                connection_state,
                                wait_seconds,
                                alert_details['response_time'],
                            )
                            if connection_state == ConnectionState.FAILED.value and time_since_alert.total_seconds() >= 30:
                                global_emergency_stop.report_api_error()
                            shutdown_event.wait(wait_seconds)
                            continue

                # Проверяем аварийный стоп
                if risk_manager.emergency_stop:
                    main_logger.warning("⛔ Аварийный стоп активен, пропускаем итерацию")
                    shutdown_event.wait(60)
                    continue
                
                # Синхронизация с биржей каждые 5 минут
                if (current_time - last_sync_time).total_seconds() > 300:
                    main_logger.info("🔄 Синхронизация позиций с биржей...")
                    for strategy_name in strategy_apis.keys():
                        api = strategy_apis[strategy_name]
                        state = strategy_states[strategy_name]
                        sync_position_with_exchange(api, state)
                    last_sync_time = current_time
                
                # Проверяем балансы и фильтруем активные стратегии
                active_strategies = []
                for strategy_name in strategy_apis.keys():
                    if shutdown_event.is_set():
                        break
                        
                    # Проверяем, не заблокирована ли стратегия
                    if strategy_name in risk_manager.blocked_strategies:
                        main_logger.info(f"🚫 Стратегия {strategy_name} заблокирована риск-менеджером")
                        continue
                    
                    api = strategy_apis[strategy_name]
                    logger = strategy_loggers[strategy_name]
                    
                    # Используем кэш балансов для снижения API запросов
                    balance_key = f"balance_{strategy_name}"
                    current_balance = balance_cache.get(balance_key)
                    if current_balance is None:
                        current_balance = get_current_balance(api)
                        balance_cache.put(balance_key, current_balance)

                    if current_balance >= 10:  # Минимум для торговли
                        active_strategies.append(strategy_name)
                        logger.debug(f"💰 Баланс: ${current_balance:.2f}")
                    else:
                        logger.warning(f"💸 Недостаточно средств: ${current_balance:.2f}")
                
                if not active_strategies:
                    main_logger.warning("⚠️ Нет активных стратегий с достаточным балансом")
                    shutdown_event.wait(60)
                    continue
                
                main_logger.info(f"✅ Активных стратегий: {len(active_strategies)}")

                # Получаем рыночные данные с кэшированием
                first_api = strategy_apis[active_strategies[0]]
                market_data_key = f"market_data_{current_time.minute // 2}"  # Кэш на 2 минуты

                all_market_data = market_data_cache.get(market_data_key)
                if all_market_data is None:
                    all_market_data = {}
                    timeframes = {
                        '1m': "1",
                        '5m': "5",
                        '15m': "15",
                        '1h': "60"
                    }

                    for tf_name, tf_value in timeframes.items():
                        try:
                            df = first_api.get_ohlcv(interval=tf_value, limit=200)
                            if df is not None and not df.empty:
                                # Конвертируем строки в числа
                                for col in ['open', 'high', 'low', 'close', 'volume']:
                                    if col in df.columns:
                                        df[col] = pd.to_numeric(df[col], errors='coerce')
                                all_market_data[tf_name] = df
                            else:
                                main_logger.warning(f"⚠️ Пустые данные для {tf_name}")
                        except Exception as e:
                            main_logger.error(f"❌ Ошибка получения данных {tf_name}: {e}")

                    # Сохраняем в кэш только если получили данные
                    if all_market_data:
                        market_data_cache.put(market_data_key, all_market_data)
                        main_logger.debug("📊 Рыночные данные обновлены и закэшированы")
                    else:
                        main_logger.debug("📊 Используем закэшированные рыночные данные")
                
                if not all_market_data:
                    main_logger.error("❌ Не удалось получить рыночные данные")
                    shutdown_event.wait(30)
                    continue
                
                # Получаем текущую цену для обновления позиций
                current_price = get_current_price(all_market_data)
                
                # Обновляем состояния позиций и риск-менеджер
                for strategy_name in active_strategies:
                    state = strategy_states[strategy_name]
                    if state.in_position:
                        state.update_position(current_price)
                    
                    # Обновляем риск-менеджер
                    current_balance = get_current_balance(strategy_apis[strategy_name])
                    update_position_in_risk_manager(
                        risk_manager, strategy_name, SYMBOL, current_price, current_balance
                    )

                # Собираем сигналы от всех стратегий
                strategy_signals = {}
                main_logger.info(f"🔍 Сбор сигналов от {len(active_strategies)} стратегий")
                
                for strategy_name in active_strategies:
                    if shutdown_event.is_set():
                        break
                        
                    api = strategy_apis[strategy_name]
                    state = strategy_states[strategy_name]
                    logger = strategy_loggers[strategy_name]
                    
                    try:
                        # Загружаем стратегию
                        strategy_factory = load_strategy(strategy_name)
                        if strategy_factory is None:
                            logger.error(f"❌ Не удалось загрузить стратегию {strategy_name}")
                            continue
                        
                        # Создаем экземпляр стратегии
                        strategy = strategy_factory()

                        # Проверяем, это стратегия v2.0 или старая
                        if hasattr(strategy, '__class__') and hasattr(strategy.__class__, '__bases__'):
                            base_classes = [cls.__name__ for cls in strategy.__class__.__bases__]
                            if 'BaseStrategy' in base_classes:
                                # Новая стратегия v2.0 - используем новую сигнатуру
                                signal = strategy.execute(all_market_data)
                            else:
                                # Старая стратегия - используем старую сигнатуру
                                signal = strategy.execute(all_market_data, state, api)
                        else:
                            # Fallback на старую сигнатуру
                            signal = strategy.execute(all_market_data, state, api)
                        
                        if signal:
                            logger.info(f"📊 Сигнал: {signal.get('signal')} по цене {signal.get('entry_price')}")
                            strategy_signals[strategy_name] = signal
                            
                            # Записываем в журнал
                            try:
                                log_trade_journal(strategy_name, signal, all_market_data)
                            except Exception as e:
                                logger.error(f"❌ Ошибка записи журнала: {e}")
                        else:
                            logger.debug("🔇 Нет сигнала")
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка выполнения стратегии {strategy_name}: {e}")
                
                main_logger.info(f"📈 Получено {len(strategy_signals)} сигналов")

                # 🚨 ПРОВЕРКА EMERGENCY STOP ПЕРЕД ОБРАБОТКОЙ СИГНАЛОВ
                trading_allowed, stop_reason = global_emergency_stop.is_trading_allowed()
                if not trading_allowed:
                    main_logger.critical(f"🚨 ТОРГОВЛЯ ЗАБЛОКИРОВАНА: {stop_reason}")
                    # Пропускаем обработку сигналов
                    time_module.sleep(60)  # Ждем минуту перед следующей проверкой
                    continue

                # 🔌 ПРОВЕРКА CIRCUIT BREAKER
                circuit_ok, circuit_reason = global_circuit_breaker.can_execute_request()
                if not circuit_ok:
                    main_logger.warning(f"🔌 CIRCUIT BREAKER: {circuit_reason}")
                    time_module.sleep(30)  # Ждем 30 секунд перед повтором
                    continue
                
                # ВЫПОЛНЕНИЕ ТОРГОВЫХ ОПЕРАЦИЙ С РИСК-МЕНЕДЖМЕНТОМ
                for strategy_name, signal in strategy_signals.items():
                    if shutdown_event.is_set():
                        break
                        
                    if not signal or signal.get('signal') not in ['BUY', 'SELL', 'EXIT_LONG', 'EXIT_SHORT']:
                        continue
                    
                    api = strategy_apis[strategy_name]
                    state = strategy_states[strategy_name]
                    logger = strategy_loggers[strategy_name]
                    
                    try:
                        signal_type = signal['signal']
                        
                        # ОБРАБОТКА СИГНАЛОВ ВХОДА
                        if signal_type in ['BUY', 'SELL']:
                            # Получаем текущий баланс
                            current_balance = get_current_balance(api)
                            
                            # Добавляем рыночные данные в сигнал
                            signal['market_data'] = all_market_data
                            
                            # КРИТИЧЕСКАЯ ПРОВЕРКА БАЛАНСА (добавлено)
                            from bot.core.balance_validator import validate_trade_balance

                            trade_amount = float(signal.get('amount', 0.001))
                            balance_ok, balance_reason = validate_trade_balance(
                                api, trade_amount, SYMBOL, leverage=1.0
                            )

                            if not balance_ok:
                                logger.error(f"💰 БЛОКИРОВКА ПО БАЛАНСУ: {balance_reason}")
                                main_logger.error(f"Стратегия {strategy_name}: {balance_reason}")
                                continue

                            # ПРОВЕРКА РИСКОВ
                            risk_ok, risk_reason = risk_manager.check_pre_trade_risk(
                                strategy_name, signal, current_balance, api
                            )

                            if not risk_ok:
                                logger.warning(f"🚫 Сделка отклонена: {risk_reason}")
                                main_logger.warning(f"Стратегия {strategy_name}: {risk_reason}")
                                continue
                            
                            # Проверяем состояние позиции
                            if state.in_position:
                                logger.info(f"⏸️ Уже в позиции {state.position_side}, пропускаем")
                                continue
                            
                            # Получаем параметры сделки
                            config = get_strategy_config(strategy_name)
                            trade_amount = config.get('trade_amount', 0.001)
                            
                            side = signal_type
                            entry_price = signal.get('entry_price', current_price)
                            stop_loss = signal.get('stop_loss')
                            take_profit = signal.get('take_profit')
                            
                            logger.info(f"🎯 Выполняем {side} по цене ${entry_price}")
                            main_logger.info(f"Стратегия {strategy_name}: {side} сделка по ${entry_price}")
                            
                            # Создаем ордер (конвертируем side в формат API)
                            api_side = 'Buy' if side == 'BUY' else 'Sell' if side == 'SELL' else side
                            
                            # Определяем тип ордера: Limit если стратегия указала конкретную цену
                            order_type = "Limit" if entry_price and entry_price > 0 else "Market"
                            price_param = entry_price if order_type == "Limit" else None
                            
                            logger.info(f"🎯 Создаем {order_type} ордер по цене ${entry_price}")
                            
                            # 🛡️ БЕЗОПАСНОЕ СОЗДАНИЕ ОРДЕРА ЧЕРЕЗ OrderManager
                            try:
                                order_manager = get_order_manager()
                                
                                order_request = OrderRequest(
                                    symbol=SYMBOL,
                                    side=api_side,
                                    order_type=order_type,
                                    qty=trade_amount,
                                    price=price_param,
                                    stop_loss=stop_loss,
                                    take_profit=take_profit,
                                    strategy_name=strategy_name
                                )
                                
                                order_response = order_manager.create_order_safe(api, order_request)
                                
                            except (OrderRejectionError, RateLimitError, EmergencyStopError) as e:
                                logger.error(f"🚫 Ордер заблокирован системой безопасности: {e}")
                                continue  # Пропускаем эту итерацию стратегии
                                
                            except Exception as e:
                                # 🛡️ ЦЕНТРАЛИЗОВАННАЯ ОБРАБОТКА ОШИБОК
                                context = ErrorContext(
                                    strategy_name=strategy_name,
                                    symbol=SYMBOL,
                                    operation="create_order"
                                )
                                handle_trading_error(e, context, RecoveryStrategy.SKIP_ITERATION)
                                continue
                            
                            if order_response and order_response.get('retCode') == 0:
                                # 🛡️ БЕЗОПАСНОЕ ОБНОВЛЕНИЕ СОСТОЯНИЯ через ThreadSafeBotState
                                bot_state = get_bot_state()
                                bot_state.set_position(
                                    symbol=SYMBOL,
                                    side=api_side,
                                    size=trade_amount,
                                    entry_price=entry_price,
                                    avg_price=entry_price
                                )
                                
                                # Обновляем локальное состояние для совместимости
                                state.in_position = True
                                state.position_side = side
                                state.entry_price = entry_price
                                state.entry_time = datetime.now(timezone.utc)
                                state.stop_loss = stop_loss
                                state.take_profit = take_profit
                                state.position_size = trade_amount
                                
                                # Устанавливаем стопы отдельно, если они не были установлены с ордером
                                if stop_loss or take_profit:
                                    try:
                                        # Ждем немного, чтобы позиция точно открылась
                                        import time
                                        time_module.sleep(1)
                                        
                                        # Устанавливаем стопы через отдельный API вызов
                                        stop_response = api.set_trading_stop(
                                            symbol=SYMBOL,
                                            stop_loss=stop_loss,
                                            take_profit=take_profit
                                        )
                                        
                                        if stop_response and stop_response.get('retCode') == 0:
                                            logger.info(f"✅ Стопы установлены: SL=${stop_loss}, TP=${take_profit}")
                                        else:
                                            error_msg = stop_response.get('retMsg', 'Unknown error') if stop_response else 'No response'
                                            logger.warning(f"⚠️ Ошибка установки стопов: {error_msg}")
                                    except Exception as e:
                                        logger.error(f"❌ Ошибка установки стопов: {e}")
                                
                                # Регистрируем в риск-менеджере
                                risk_manager.register_trade(strategy_name, signal, order_response)
                                
                                # 🛡️ БЕЗОПАСНОЕ ЛОГИРОВАНИЕ без утечек API данных
                                secure_logger = get_secure_logger('trader')
                                secure_logger.safe_log_api_response(
                                    order_response,
                                    f"✅ Позиция {strategy_name} открыта",
                                    f"❌ Ошибка открытия позиции {strategy_name}"
                                )
                                main_logger.info(f"Стратегия {strategy_name}: позиция открыта и зарегистрирована")
                                
                                # Отправляем уведомление о позиции
                                if telegram_bot:
                                    try:
                                        signal_strength = signal.get('signal_strength')
                                        comment = signal.get('comment', '')
                                        send_position_notification(
                                            telegram_bot, side, strategy_name, entry_price,
                                            stop_loss, take_profit, trade_amount,
                                            signal_strength, comment
                                        )
                                    except Exception as e:
                                        logger.error(f"❌ Ошибка отправки уведомления: {e}")
                                
                                # Логируем сделку
                                api.log_trade(
                                    symbol=SYMBOL,
                                    side=side,
                                    qty=trade_amount,
                                    entry_price=entry_price,
                                    exit_price=0,
                                    pnl=0,
                                    stop_loss=stop_loss,
                                    take_profit=take_profit,
                                    strategy=signal.get('strategy', strategy_name),
                                    comment=signal.get('comment', '')
                                )
                            else:
                                error_msg = order_response.get('retMsg', 'Unknown error') if order_response else 'No response'
                                logger.error(f"❌ Ошибка создания ордера: {error_msg}")
                                main_logger.error(f"Стратегия {strategy_name}: ошибка ордера - {error_msg}")
                        
                        # ОБРАБОТКА СИГНАЛОВ ВЫХОДА
                        elif signal_type in ['EXIT_LONG', 'EXIT_SHORT']:
                            if not state.in_position:
                                logger.info("❌ Нет открытой позиции для закрытия")
                                continue
                            
                            # Проверяем соответствие сигнала позиции
                            if ((signal_type == 'EXIT_LONG' and state.position_side != 'BUY') or
                                (signal_type == 'EXIT_SHORT' and state.position_side != 'SELL')):
                                logger.warning(f"⚠️ Неправильный сигнал выхода {signal_type} для позиции {state.position_side}")
                                continue
                            
                            # Определяем сторону закрытия (конвертируем в формат API)
                            close_side = 'SELL' if state.position_side == 'BUY' else 'BUY'
                            api_close_side = 'Sell' if close_side == 'SELL' else 'Buy'
                            
                            logger.info(f"🔚 Закрываем позицию {state.position_side} сигналом {signal_type}")
                            
                            # 🛡️ БЕЗОПАСНОЕ ЗАКРЫТИЕ ПОЗИЦИИ ЧЕРЕЗ OrderManager
                            try:
                                order_manager = get_order_manager()
                                
                                close_request = OrderRequest(
                                    symbol=SYMBOL,
                                    side=api_close_side,
                                    order_type="Market",
                                    qty=state.position_size,
                                    reduce_only=True,
                                    strategy_name=strategy_name
                                )
                                
                                close_response = order_manager.create_order_safe(api, close_request)
                                
                            except (OrderRejectionError, RateLimitError, EmergencyStopError) as e:
                                logger.error(f"🚫 Закрытие позиции заблокировано: {e}")
                                continue
                                
                            except Exception as e:
                                # 🛡️ ЦЕНТРАЛИЗОВАННАЯ ОБРАБОТКА ОШИБОК 
                                context = ErrorContext(
                                    strategy_name=strategy_name,
                                    symbol=SYMBOL, 
                                    operation="close_position"
                                )
                                handle_trading_error(e, context, RecoveryStrategy.SKIP_ITERATION)
                                continue
                            
                            if close_response and close_response.get('retCode') == 0:
                                # Вычисляем P&L
                                exit_price = current_price
                                realized_pnl = state.unrealized_pnl
                                
                                # Вычисляем длительность позиции
                                duration = None
                                if state.entry_time:
                                    duration = str(datetime.now(timezone.utc) - state.entry_time).split('.')[0]
                                
                                # Обновляем риск-менеджер
                                risk_manager.close_position(
                                    strategy_name, SYMBOL, exit_price, realized_pnl
                                )
                                
                                logger.info(f"✅ Позиция закрыта, P&L: ${realized_pnl:.2f}")
                                main_logger.info(f"Стратегия {strategy_name}: позиция закрыта, P&L: ${realized_pnl:.2f}")
                                
                                # Отправляем уведомление о закрытии позиции
                                if telegram_bot:
                                    try:
                                        send_position_close_notification(
                                            telegram_bot, strategy_name, state.position_side,
                                            exit_price, realized_pnl, state.entry_price, duration
                                        )
                                    except Exception as e:
                                        logger.error(f"❌ Ошибка отправки уведомления о закрытии: {e}")
                                
                                # Сбрасываем состояние
                                state.reset()
                            else:
                                error_msg = close_response.get('retMsg', 'Unknown error') if close_response else 'No response'
                                logger.error(f"❌ Ошибка закрытия позиции: {error_msg}")
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки сигнала {signal_type}: {e}")
                
                # НЕЙРОННАЯ СЕТЬ
                if strategy_signals:
                    try:
                        # Получаем рекомендацию от нейронки
                        neural_recommendation = neural_integration.make_neural_recommendation(
                            all_market_data, strategy_signals
                        )
                        
                        if neural_recommendation:
                            main_logger.info(f"🧠 Нейронка рекомендует {neural_recommendation['strategy']} "
                                           f"(уверенность: {neural_recommendation['confidence']:.3f})")
                            
                            # Размещаем ставку
                            neural_bet = neural_integration.place_neural_bet(all_market_data, strategy_signals)
                            if neural_bet:
                                main_logger.info(f"🎲 Нейронная ставка: {neural_bet['bet_id']}")
                        
                        # Очищаем старые ставки и сохраняем состояние
                        neural_integration.cleanup_old_bets()
                        neural_integration.save_state()
                        
                    except Exception as e:
                        main_logger.error(f"❌ Ошибка нейронной сети: {e}")
                
                # === БЛОК А2: ПЕРИОДИЧЕСКАЯ ОЧИСТКА ПАМЯТИ ===
                # Каждые 10 итераций очищаем кэши и принудительно собираем мусор
                if iteration_count % 10 == 0:
                    import gc
                    market_data_cache.clear()
                    strategy_results_cache.clear()
                    balance_cache.clear()
                    position_cache.clear()
                    gc.collect()
                    main_logger.info(f"🗂️ Очистка памяти выполнена (итерация #{iteration_count})")

                # Пауза между итерациями
                main_logger.debug("⏳ Пауза 30 секунд...")
                shutdown_event.wait(30)
                
            except KeyboardInterrupt:
                main_logger.info("⏹️ Получен сигнал остановки")
                break
            except Exception as e:
                main_logger.error(f"💥 Критическая ошибка в торговом цикле: {e}", exc_info=True)
                shutdown_event.wait(60)
    
    except Exception as e:
        main_logger.error(f"💥 Фатальная ошибка инициализации торгового цикла: {e}", exc_info=True)
    
    finally:
        main_logger.info("🛑 Торговый цикл завершен")

# Экспортируем функцию для обратной совместимости
def run_trading():
    """Функция для обратной совместимости с существующим main.py"""
    # Создаем базовый риск-менеджер
    risk_manager = RiskManager()
    
    # Создаем event для остановки
    shutdown_event = threading.Event()
    
    # Запускаем торговый цикл
    run_trading_with_risk_management(risk_manager, shutdown_event)

if __name__ == "__main__":
    # Прямой запуск для тестирования
    run_trading()
