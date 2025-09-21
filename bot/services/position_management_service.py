# bot/services/position_management_service.py
"""
📈 СЕРВИС УПРАВЛЕНИЯ ПОЗИЦИЯМИ
Централизованное управление открытием и закрытием позиций
"""

import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from bot.core.secure_logger import get_secure_logger
from bot.core.order_manager import get_order_manager, OrderRequest
from bot.core.thread_safe_state import get_bot_state
from bot.core.error_handler import handle_trading_error, ErrorContext, RecoveryStrategy
from bot.core.exceptions import OrderRejectionError, RateLimitError, EmergencyStopError


class PositionManagementService:
    """
    📈 Сервис для управления торговыми позициями
    """
    
    def __init__(self):
        """Инициализация сервиса управления позициями"""
        self.logger = get_secure_logger('position_management')
        self.order_manager = get_order_manager()
        self.bot_state = get_bot_state()
    
    def open_position(self, api, signal: Dict[str, Any], strategy_name: str, 
                     trade_amount: float, current_price: float, state) -> Optional[Dict[str, Any]]:
        """
        Открытие торговой позиции
        
        Args:
            api: API экземпляр
            signal: Торговый сигнал
            strategy_name: Название стратегии
            trade_amount: Размер позиции
            current_price: Текущая цена
            state: Состояние стратегии
            
        Returns:
            Dict: Ответ от API или None в случае ошибки
        """
        try:
            signal_type = signal['signal_type']
            entry_price = signal.get('entry_price', current_price)
            stop_loss = signal.get('stop_loss')
            take_profit = signal.get('take_profit')
            
            # Определяем сторону ордера
            side = signal_type.replace('ENTER_', '')
            api_side = 'Buy' if side == 'LONG' else 'Sell'
            
            self.logger.info(f"🎯 Открываем позицию {strategy_name}: {side} ${trade_amount} по цене ${entry_price}")
            
            # 🛡️ БЕЗОПАСНОЕ СОЗДАНИЕ ОРДЕРА ЧЕРЕЗ OrderManager
            order_request = OrderRequest(
                symbol="BTCUSDT",
                side=api_side,
                order_type="Market",
                qty=trade_amount,
                price=None,  # Рыночный ордер
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy_name=strategy_name
            )
            
            order_response = self.order_manager.create_order_safe(api, order_request)
            
            if order_response and order_response.get('retCode') == 0:
                # Обновляем состояние через thread-safe механизм
                self.bot_state.set_position(
                    symbol="BTCUSDT",
                    side=api_side,
                    size=trade_amount,
                    entry_price=entry_price,
                    avg_price=entry_price,
                    strategy_name=strategy_name
                )
                
                # Обновляем локальное состояние для совместимости
                state.in_position = True
                state.position_side = side
                state.entry_price = entry_price
                state.entry_time = datetime.now(timezone.utc)
                state.stop_loss = stop_loss
                state.take_profit = take_profit
                state.position_size = trade_amount
                
                # Устанавливаем стопы отдельно
                self._set_stops_if_needed(api, stop_loss, take_profit)
                
                self.logger.info(f"✅ Позиция {strategy_name} открыта успешно")
                return order_response
            else:
                error_msg = order_response.get('retMsg', 'Unknown error') if order_response else 'No response'
                self.logger.error(f"❌ Ошибка создания ордера: {error_msg}")
                return None
                
        except (OrderRejectionError, RateLimitError, EmergencyStopError) as e:
            self.logger.error(f"🚫 Открытие позиции заблокировано: {e}")
            return None
            
        except Exception as e:
            context = ErrorContext(
                strategy_name=strategy_name,
                symbol="BTCUSDT",
                operation="open_position"
            )
            handle_trading_error(e, context, RecoveryStrategy.SKIP_ITERATION)
            return None
    
    def close_position(self, api, state, strategy_name: str, signal_type: str, 
                      current_price: float) -> Optional[Dict[str, Any]]:
        """
        Закрытие торговой позиции
        
        Args:
            api: API экземпляр
            state: Состояние стратегии
            strategy_name: Название стратегии
            signal_type: Тип сигнала выхода
            current_price: Текущая цена
            
        Returns:
            Dict: Ответ от API или None в случае ошибки
        """
        try:
            if not state.in_position:
                self.logger.warning("❌ Нет открытой позиции для закрытия")
                return None
            
            # Проверяем соответствие сигнала позиции
            if ((signal_type == 'EXIT_LONG' and state.position_side != 'BUY') or
                (signal_type == 'EXIT_SHORT' and state.position_side != 'SELL')):
                self.logger.warning(f"⚠️ Неправильный сигнал выхода {signal_type} для позиции {state.position_side}")
                return None
            
            # Определяем сторону закрытия
            close_side = 'SELL' if state.position_side == 'BUY' else 'BUY'
            api_close_side = 'Sell' if close_side == 'SELL' else 'Buy'
            
            self.logger.info(f"🔚 Закрываем позицию {strategy_name}: {state.position_side} -> {api_close_side}")
            
            # 🛡️ БЕЗОПАСНОЕ ЗАКРЫТИЕ ПОЗИЦИИ ЧЕРЕЗ OrderManager
            close_request = OrderRequest(
                symbol="BTCUSDT",
                side=api_close_side,
                order_type="Market",
                qty=state.position_size,
                reduce_only=True,
                strategy_name=strategy_name
            )
            
            close_response = self.order_manager.create_order_safe(api, close_request)
            
            if close_response and close_response.get('retCode') == 0:
                # Вычисляем P&L и длительность
                exit_price = current_price
                realized_pnl = self._calculate_pnl(state, exit_price)
                duration = self._calculate_duration(state)
                
                # Сбрасываем состояние
                state.reset()
                self.bot_state.clear_position("BTCUSDT")
                
                self.logger.info(f"✅ Позиция {strategy_name} закрыта, P&L: ${realized_pnl:.2f}")
                
                # Добавляем информацию о закрытии в ответ
                close_response['pnl'] = realized_pnl
                close_response['exit_price'] = exit_price
                close_response['duration'] = duration
                
                return close_response
            else:
                error_msg = close_response.get('retMsg', 'Unknown error') if close_response else 'No response'
                self.logger.error(f"❌ Ошибка закрытия позиции: {error_msg}")
                return None
                
        except (OrderRejectionError, RateLimitError, EmergencyStopError) as e:
            self.logger.error(f"🚫 Закрытие позиции заблокировано: {e}")
            return None
            
        except Exception as e:
            context = ErrorContext(
                strategy_name=strategy_name,
                symbol="BTCUSDT",
                operation="close_position"
            )
            handle_trading_error(e, context, RecoveryStrategy.SKIP_ITERATION)
            return None
    
    def _set_stops_if_needed(self, api, stop_loss: Optional[float],
                           take_profit: Optional[float]) -> None:
        """
        Установка стоп-лосс и тейк-профит если необходимо

        Args:
            api: API экземпляр
            stop_loss: Уровень стоп-лосс
            take_profit: Уровень тейк-профит
        """
        if not (stop_loss or take_profit):
            self.logger.info("🔄 Стопы не установлены - не переданы параметры SL/TP")
            return

        try:
            # Логируем попытку установки стопов
            if stop_loss and take_profit:
                self.logger.info(f"🎯 Устанавливаем стопы: SL=${stop_loss:.2f}, TP=${take_profit:.2f}")
            elif stop_loss:
                self.logger.info(f"🛑 Устанавливаем только SL: ${stop_loss:.2f}")
            elif take_profit:
                self.logger.info(f"🎯 Устанавливаем только TP: ${take_profit:.2f}")

            # Ждем больше времени для корректного открытия позиции
            time.sleep(2)

            # Повторные попытки установки стопов (до 3 попыток)
            max_attempts = 3
            for attempt in range(max_attempts):
                stop_response = api.set_trading_stop(
                    symbol="BTCUSDT",
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )

                if stop_response and stop_response.get('retCode') == 0:
                    self.logger.info(f"✅ Стопы установлены успешно (попытка {attempt + 1})")
                    return
                else:
                    error_msg = stop_response.get('retMsg', 'Unknown error') if stop_response else 'No response'
                    self.logger.warning(f"⚠️ Ошибка установки стопов (попытка {attempt + 1}): {error_msg}")

                    if attempt < max_attempts - 1:
                        self.logger.info(f"🔄 Повторная попытка через 1 секунду...")
                        time.sleep(1)

            # Если все попытки неудачны
            self.logger.error(f"❌ Не удалось установить стопы после {max_attempts} попыток")

        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка установки стопов: {e}")
    
    def _calculate_pnl(self, state, exit_price: float) -> float:
        """
        Расчет прибыли/убытка
        
        Args:
            state: Состояние позиции
            exit_price: Цена выхода
            
        Returns:
            float: Размер P&L
        """
        try:
            if not state.entry_price or not state.position_size:
                return 0.0
            
            if state.position_side == 'BUY':
                pnl = (exit_price - state.entry_price) * state.position_size
            else:
                pnl = (state.entry_price - exit_price) * state.position_size
            
            return round(pnl, 2)
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета P&L: {e}")
            return 0.0
    
    def _calculate_duration(self, state) -> Optional[str]:
        """
        Расчет длительности позиции
        
        Args:
            state: Состояние позиции
            
        Returns:
            str: Длительность в формате строки
        """
        try:
            if state.entry_time:
                duration = datetime.now(timezone.utc) - state.entry_time
                return str(duration).split('.')[0]  # Убираем микросекунды
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета длительности: {e}")
        
        return None
    
    def sync_position_with_exchange(self, api, state) -> None:
        """
        Синхронизация позиции с биржей
        
        Args:
            api: API экземпляр
            state: Состояние стратегии
        """
        try:
            positions = api.get_positions("BTCUSDT")
            
            if positions and positions.get('retCode') == 0:
                position_list = positions['result']['list']
                
                if position_list:
                    pos = position_list[0]
                    exchange_size = float(pos.get('size', 0))
                    
                    if exchange_size > 0:
                        # Есть позиция на бирже - синхронизируем состояние
                        state.in_position = True
                        state.position_size = exchange_size
                        state.entry_price = float(pos.get('avgPrice', 0))
                        state.position_side = pos.get('side', 'Buy')
                        
                        self.logger.info(f"🔄 Синхронизация: размер={exchange_size}, цена={state.entry_price}")
                    else:
                        # Нет позиции на бирже - сбрасываем состояние
                        if state.in_position:
                            self.logger.warning("⚠️ Позиция закрыта на бирже, сбрасываем состояние")
                            state.reset()
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка синхронизации с биржей: {e}")


# Глобальный экземпляр сервиса
_position_service = None


def get_position_service():
    """
    Получение глобального экземпляра сервиса управления позициями
    
    Returns:
        PositionManagementService: Экземпляр сервиса
    """
    global _position_service
    
    if _position_service is None:
        _position_service = PositionManagementService()
    
    return _position_service