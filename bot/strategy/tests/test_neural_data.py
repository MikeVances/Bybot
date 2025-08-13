#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.ai import NeuralIntegration

def test_neural_data():
    """Тестируем получение данных нейронки"""
    
    print("Тестируем получение данных нейронки...")
    
    try:
        # Создаем экземпляр нейронной интеграции
        neural_integration = NeuralIntegration()
        print("✅ NeuralIntegration создан")
        
        # Получаем статистику
        stats = neural_integration.get_neural_statistics()
        print("✅ Статистика получена")
        
        neural_stats = stats['neural_trader']
        strategy_analysis = stats['strategy_analysis']
        
        print(f"📊 Статистика нейронки:")
        print(f"   💰 Баланс: ${neural_stats['current_balance']:.2f}")
        print(f"   📈 Прибыль: ${neural_stats['profit']:.2f}")
        print(f"   📊 ROI: {neural_stats['roi']:.1f}%")
        print(f"   🎯 Ставок: {neural_stats['total_bets']}")
        print(f"   ✅ Успешных: {neural_stats['winning_bets']}")
        print(f"   📈 Винрейт: {neural_stats['win_rate']:.1f}%")
        
        print(f"\n📋 Анализ стратегий:")
        for strategy_name, data in strategy_analysis.items():
            print(f"   {strategy_name}:")
            print(f"      📊 Сигналов: {data['total_signals']}")
            print(f"      ✅ Успешность: {data['success_rate']*100:.1f}%")
            print(f"      💰 Прибыль: {data['avg_profit']*100:.2f}%")
            print(f"      🟢 Покупки: {data['buy_signals']} | 🔴 Продажи: {data['sell_signals']}")
        
        # Получаем ранжирование стратегий
        ranking = neural_integration.get_strategy_ranking()
        print(f"\n🏆 Ранжирование стратегий:")
        for i, strategy in enumerate(ranking[:5], 1):
            print(f"   {i}. {strategy['strategy']}")
            print(f"      📊 Сигналов: {strategy['total_signals']}")
            print(f"      ✅ Успешность: {strategy['success_rate']*100:.1f}%")
            print(f"      💰 Прибыль: {strategy['avg_profit']*100:.2f}%")
        
        print(f"\n🔥 Активные ставки: {stats['active_bets']}")
        print(f"📋 Завершенных сделок: {stats['completed_trades']}")
        
        print("\n✅ Все данные нейронки получены корректно!")
        
    except Exception as e:
        print(f"❌ Ошибка при получении данных нейронки: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_neural_data() 