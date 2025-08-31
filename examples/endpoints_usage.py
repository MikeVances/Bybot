#!/usr/bin/env python3
"""
Пример использования перечислений эндпоинтов Bybit API
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.exchange.endpoints import Position, Trade, Account, Market
# REMOVED DANGEROUS v4 API IMPORT - USE ONLY v5


def main():
    """Демонстрация использования перечислений эндпоинтов"""
    
    print("=== Демонстрация перечислений эндпоинтов Bybit API ===\n")
    
    # Показываем доступные эндпоинты
    print("1. Эндпоинты позиций:")
    for endpoint in Position:
        print(f"   {endpoint.name}: {endpoint.value}")
    
    print("\n2. Эндпоинты торговли:")
    for endpoint in Trade:
        print(f"   {endpoint.name}: {endpoint.value}")
    
    print("\n3. Эндпоинты аккаунта:")
    for endpoint in Account:
        print(f"   {endpoint.name}: {endpoint.value}")
    
    print("\n4. Эндпоинты рынка:")
    for endpoint in Market:
        print(f"   {endpoint.name}: {endpoint.value}")
    
    print("\n=== Примеры использования ===")
    
    # Создаем экземпляр API (без реальных запросов)
    api = BybitAPI()
    
    print(f"\n5. Пример создания ордера:")
    print(f"   endpoint: {Trade.PLACE_ORDER}")
    print(f"   method: POST")
    print(f"   params: {{'category': 'linear', 'symbol': 'BTCUSDT', 'side': 'Buy'}}")
    
    print(f"\n6. Пример получения позиций:")
    print(f"   endpoint: {Position.GET_POSITIONS}")
    print(f"   method: GET")
    print(f"   params: {{'category': 'linear', 'accountType': 'UNIFIED'}}")
    
    print(f"\n7. Пример установки стоп-лосса:")
    print(f"   endpoint: {Position.SET_TRADING_STOP}")
    print(f"   method: POST")
    print(f"   params: {{'category': 'linear', 'symbol': 'BTCUSDT', 'stopLoss': '117520.60'}}")
    
    print(f"\n8. Пример получения баланса:")
    print(f"   endpoint: {Account.GET_WALLET_BALANCE}")
    print(f"   method: GET")
    print(f"   params: {{'accountType': 'UNIFIED'}}")
    
    print(f"\n9. Пример получения времени сервера:")
    print(f"   endpoint: {Market.GET_SERVER_TIME}")
    print(f"   method: GET")
    print(f"   params: {{}}")
    
    print(f"\n10. Пример получения OHLCV:")
    print(f"   endpoint: {Market.GET_KLINE}")
    print(f"   method: GET")
    print(f"   params: {{'category': 'linear', 'symbol': 'BTCUSDT', 'interval': '1', 'limit': 100}}")
    
    print(f"\n11. Пример получения ставок финансирования:")
    print(f"   endpoint: {Market.GET_FUNDING_RATE_HISTORY}")
    print(f"   method: GET")
    print(f"   params: {{'category': 'linear', 'symbol': 'BTCUSDT', 'limit': 100}}")
    
    print("\n=== Преимущества использования перечислений ===")
    print("✅ Типобезопасность - IDE проверяет правильность")
    print("✅ Автодополнение - IDE предлагает доступные эндпоинты")
    print("✅ Централизованное управление - все в одном месте")
    print("✅ Легкость рефакторинга - изменение в одном месте")
    print("✅ Самодокументируемость - понятные названия")


if __name__ == "__main__":
    main() 