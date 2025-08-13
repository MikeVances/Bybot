#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.ai.neural_integration import NeuralIntegration
import pandas as pd
import numpy as np

def test_neural_integration():
    """Тестируем работу нейронной интеграции с 10 стратегиями"""
    
    # Создаем тестовые данные
    base_price = 117000
    base_volume = 1000
    
    # Генерируем 100 строк данных
    opens = [base_price + i * 15 for i in range(100)]
    highs = [price + 50 for price in opens]
    lows = [price - 50 for price in opens]
    closes = [price + 100 for price in opens]
    volumes = [base_volume + i * 10 for i in range(100)]
    volumes[-1] = base_volume * 10  # Большой объем в конце
    
    test_data = {
        '1m': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }),
        '5m': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }),
        '15m': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }),
        '1h': pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })
    }
    
    # Создаем тестовые сигналы для всех 10 стратегий
    strategy_signals = {
        'strategy_01': {
            'signal': 'BUY',
            'entry_price': 118585.0,
            'stop_loss': 118382.5,
            'take_profit': 118888.8,
            'strategy': 'VolumeSpike_VWAP_Optimized',
            'comment': 'Вход в лонг'
        },
        'strategy_02': {
            'signal': 'SELL',
            'entry_price': 117500.0,
            'stop_loss': 117700.0,
            'take_profit': 117200.0,
            'strategy': 'Strategy02',
            'comment': 'Вход в шорт'
        },
        'strategy_03': None,  # Нет сигнала
        'strategy_04': None,  # Нет сигнала
        'strategy_05': {
            'signal': 'BUY',
            'entry_price': 118000.0,
            'stop_loss': 117800.0,
            'take_profit': 118300.0,
            'strategy': 'Strategy05',
            'comment': 'Вход в лонг'
        },
        'strategy_06': None,  # Нет сигнала
        'strategy_07': None,  # Нет сигнала
        'strategy_08': None,  # Заглушка
        'strategy_09': None,  # Заглушка
        'strategy_10': None   # Заглушка
    }
    
    print("Тестируем нейронную интеграцию...")
    
    try:
        # Создаем экземпляр нейронной интеграции
        neural_integration = NeuralIntegration()
        
        print(f"Нейронная интеграция создана")
        print(f"Количество активных сигналов: {len([s for s in strategy_signals.values() if s is not None])}")
        
        # Получаем рекомендацию от нейронки
        recommendation = neural_integration.make_neural_recommendation(test_data, strategy_signals)
        
        if recommendation:
            print(f"Нейронка рекомендует: {recommendation['strategy']}")
            print(f"Уверенность: {recommendation['confidence']:.3f}")
            print(f"Нейронный скор: {recommendation['neural_score']:.3f}")
            print(f"Исторический скор: {recommendation['historical_score']:.3f}")
            print(f"Все рекомендации:")
            for strategy, data in recommendation['all_recommendations'].items():
                print(f"  {strategy}: {data['combined_score']:.3f}")
        else:
            print("Нейронка не дала рекомендации")
        
        # Размещаем ставку
        bet = neural_integration.place_neural_bet(test_data, strategy_signals)
        
        if bet:
            print(f"Размещена ставка: {bet['bet_id']}")
            print(f"Стратегия: {bet['strategy']}")
            print(f"Уверенность: {bet['confidence']:.3f}")
        else:
            print("Ставка не размещена")
        
        # Получаем статистику
        stats = neural_integration.get_neural_statistics()
        print(f"Статистика нейронки: {stats}")
        
    except Exception as e:
        print(f"Ошибка при тестировании нейронной интеграции: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_neural_integration() 