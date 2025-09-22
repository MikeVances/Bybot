"""
Модуль глобальной проверки баланса и защиты от финансовых рисков
Предотвращает сделки при недостаточном балансе или превышении лимитов
"""

import logging
from typing import Dict, Optional, Tuple
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)


class BalanceValidator:
    """
    Глобальный валидатор баланса для всех стратегий
    Предотвращает margin call и принудительную ликвидацию
    """

    def __init__(self):
        self.min_balance_reserve = 0.05  # 5% резерв баланса (было 10% - слишком строго)
        self.max_leverage_multiplier = 0.8  # Используем только 80% от максимального плеча
        self.emergency_balance_threshold = 0.02  # 2% - критический уровень баланса

    def validate_trade_balance(
        self,
        api,
        trade_amount: float,
        symbol: str = "BTCUSDT",
        leverage: float = 1.0
    ) -> Tuple[bool, str, Dict]:
        """
        Глобальная проверка баланса перед торговой операцией

        Args:
            api: API клиент биржи
            trade_amount: Размер позиции в базовой валюте
            symbol: Торговая пара
            leverage: Используемое плечо

        Returns:
            Tuple[bool, str, Dict]: (можно_торговать, причина, детали_баланса)
        """
        try:
            # Получаем текущий баланс
            balance_info = self._get_wallet_balance(api)
            if not balance_info:
                return False, "❌ Не удалось получить данные баланса", {}

            available_balance = balance_info.get('available_balance', 0)
            used_margin = balance_info.get('used_margin', 0)
            total_equity = balance_info.get('total_equity', 0)

            # Рассчитываем необходимый маржин для сделки
            required_margin = self._calculate_required_margin(
                trade_amount, leverage, symbol
            )

            # Проверка 1: Достаточно ли свободного баланса
            balance_after_trade = available_balance - required_margin
            # Используем USDT баланс для резерва, а не весь эквити (который включает BTC)
            usdt_balance = balance_info.get('usdt_balance', available_balance)
            min_required_balance = usdt_balance * self.min_balance_reserve

            logger.debug(f"💰 Проверка баланса: после_сделки={balance_after_trade:.2f}, мин_резерв={min_required_balance:.2f}")

            if balance_after_trade < min_required_balance:
                return False, f"❌ Недостаточно баланса. Требуется: {required_margin:.4f}, доступно: {available_balance:.4f}", balance_info

            # Проверка 2: Критический уровень баланса
            if total_equity < (balance_info.get('initial_equity', total_equity) * self.emergency_balance_threshold):
                return False, "🚨 КРИТИЧЕСКИЙ УРОВЕНЬ БАЛАНСА! Торговля остановлена", balance_info

            # Проверка 3: Проверяем общий риск портфеля
            total_margin_after = used_margin + required_margin
            max_allowed_margin = total_equity * self.max_leverage_multiplier

            if total_margin_after > max_allowed_margin:
                return False, f"❌ Превышение лимита плеча. Общий маржин: {total_margin_after:.4f}, лимит: {max_allowed_margin:.4f}", balance_info

            # Проверка 4: Размер позиции не должен превышать разумные лимиты
            position_value = trade_amount * self._get_current_price(api, symbol)
            max_position_value = total_equity * 0.2  # Максимум 20% от капитала на одну позицию

            if position_value > max_position_value:
                return False, f"❌ Слишком большая позиция. Размер: {position_value:.2f}, лимит: {max_position_value:.2f}", balance_info

            # Все проверки пройдены
            logger.info(f"✅ Проверка баланса пройдена. Доступно: {available_balance:.4f}, требуется: {required_margin:.4f}")

            return True, "✅ Баланс достаточен для торговли", balance_info

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке баланса: {e}")
            return False, f"❌ Ошибка проверки баланса: {str(e)}", {}

    def _get_wallet_balance(self, api) -> Optional[Dict]:
        """Получить данные кошелька с обработкой ошибок"""
        try:
            # Для Bybit API v5
            response = api.get_wallet_balance_v5()

            if response['retCode'] != 0:
                logger.error(f"❌ Ошибка API при получении баланса: {response['retMsg']}")
                return None

            # Извлекаем данные USDT баланса
            account_data = response['result']['list'][0] if response['result']['list'] else {}
            usdt_coin = next((coin for coin in account_data.get('coin', []) if coin['coin'] == 'USDT'), {})

            # Безопасная конвертация строк в float
            def safe_float(value, default=0.0):
                try:
                    if value == '' or value is None:
                        return default
                    return float(value)
                except (ValueError, TypeError):
                    return default

            # Используем глобальные данные аккаунта вместо USDT-специфичных
            total_available_balance = safe_float(account_data.get('totalAvailableBalance', 0))
            total_margin_balance = safe_float(account_data.get('totalMarginBalance', 0))
            total_equity = safe_float(account_data.get('totalEquity', 0))
            wallet_balance = safe_float(usdt_coin.get('walletBalance', 0))

            return {
                'available_balance': total_available_balance,  # Общий доступный баланс
                'used_margin': total_margin_balance - wallet_balance,
                'total_equity': total_equity,  # Общий эквити (включая все валюты в USD)
                'initial_equity': total_equity,  # Сохраняем начальный капитал
                'usdt_balance': wallet_balance  # USDT баланс для расчета резерва
            }

        except Exception as e:
            logger.error(f"❌ Исключение при получении баланса: {e}")
            return None

    def _calculate_required_margin(self, trade_amount: float, leverage: float, symbol: str) -> float:
        """Рассчитать необходимый маржин для позиции"""
        try:
            # Для получения цены нам нужен API, но пока используем приблизительную
            # TODO: передавать API объект для получения реальной цены
            current_price = 114500.0  # Примерная цена BTC на сегодня
            logger.debug(f"💰 Расчет маржина: amount={trade_amount}, price=${current_price:.2f}, leverage={leverage}")

            position_value = trade_amount * current_price
            required_margin = position_value / max(leverage, 1.0)

            # Добавляем буфер 10% на комиссии и проскальзывание
            final_margin = required_margin * 1.1

            logger.debug(f"💰 Позиция: ${position_value:.2f}, маржин: ${required_margin:.2f}, итого: ${final_margin:.2f}")
            return final_margin

        except Exception as e:
            logger.error(f"❌ Ошибка расчета маржина: {e}")
            # Используем консервативную оценку с примерной ценой $100k
            return trade_amount * 100000 * 1.1

    def _get_current_price(self, api, symbol: str) -> float:
        """Получить текущую цену символа"""
        try:
            response = api.get_tickers(category="linear", symbol=symbol)
            if response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['lastPrice'])
            return 50000.0  # Дефолтная цена для BTC
        except:
            return 50000.0

    def check_emergency_stop_conditions(self, api) -> Tuple[bool, str]:
        """
        Проверить условия экстренной остановки торговли

        Returns:
            Tuple[bool, str]: (нужна_остановка, причина)
        """
        try:
            balance_info = self._get_wallet_balance(api)
            if not balance_info:
                return True, "❌ Не удалось получить данные баланса"

            total_equity = balance_info.get('total_equity', 0)
            initial_equity = balance_info.get('initial_equity', total_equity)

            # Проверка критической потери капитала
            if total_equity < initial_equity * self.emergency_balance_threshold:
                return True, f"🚨 КРИТИЧЕСКАЯ ПОТЕРЯ КАПИТАЛА! Текущий: {total_equity:.2f}, было: {initial_equity:.2f}"

            # Проверка margin level
            available_balance = balance_info.get('available_balance', 0)
            if available_balance <= 0:
                return True, "🚨 ОТРИЦАТЕЛЬНЫЙ ДОСТУПНЫЙ БАЛАНС!"

            return False, "✅ Все условия в норме"

        except Exception as e:
            logger.error(f"❌ Ошибка проверки emergency stop: {e}")
            return True, f"❌ Ошибка проверки: {str(e)}"


# Глобальный экземпляр валидатора
global_balance_validator = BalanceValidator()


def validate_trade_balance(api, trade_amount: float, symbol: str = "BTCUSDT", leverage: float = 1.0) -> Tuple[bool, str]:
    """
    Удобная функция для быстрой проверки баланса

    Returns:
        Tuple[bool, str]: (можно_торговать, причина)
    """
    is_valid, reason, _ = global_balance_validator.validate_trade_balance(api, trade_amount, symbol, leverage)
    return is_valid, reason


def check_emergency_stop(api) -> Tuple[bool, str]:
    """
    Удобная функция для проверки экстренной остановки

    Returns:
        Tuple[bool, str]: (нужна_остановка, причина)
    """
    return global_balance_validator.check_emergency_stop_conditions(api)