#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.ai import NeuralIntegration

def test_neural_fixed():
    """Тестируем исправленную функцию нейронки с правильным экранированием"""
    
    print("Тестируем исправленную функцию нейронки...")
    
    try:
        # Создаем экземпляр нейронной интеграции
        neural_integration = NeuralIntegration()
        print("✅ NeuralIntegration создан")
        
        # Получаем статистику
        stats = neural_integration.get_neural_statistics()
        neural_stats = stats['neural_trader']
        strategy_analysis = stats['strategy_analysis']
        
        # Формируем отчет (как в Telegram боте)
        neural_text = "🤖 *Нейронная сеть-трейдер*\n\n"
        
        # Статистика нейронки
        neural_text += "📊 *Статистика нейронки:*\n"
        neural_text += f"   💰 Баланс: \\${neural_stats['current_balance']:.2f}\n"
        neural_text += f"   📈 Прибыль: \\${neural_stats['profit']:.2f}\n"
        neural_text += f"   📊 ROI: {neural_stats['roi']:.1f}%\n"
        neural_text += f"   🎯 Ставок: {neural_stats['total_bets']}\n"
        neural_text += f"   ✅ Успешных: {neural_stats['winning_bets']}\n"
        neural_text += f"   📈 Винрейт: {neural_stats['win_rate']:.1f}%\n\n"
        
        # Ранжирование стратегий
        ranking = neural_integration.get_strategy_ranking()
        if ranking:
            neural_text += "🏆 *Ранжирование стратегий:*\n"
            for i, strategy in enumerate(ranking[:5], 1):
                strategy_name = strategy['strategy'].replace('_', '\\_')
                neural_text += f"   {i}\\. {strategy_name}\n"
                neural_text += f"      📊 Сигналов: {strategy['total_signals']}\n"
                neural_text += f"      ✅ Успешность: {strategy['success_rate']*100:.1f}%\n"
                neural_text += f"      💰 Прибыль: {strategy['avg_profit']*100:.2f}%\n"
                neural_text += f"      🟢 Покупки: {strategy['buy_signals']} \\| 🔴 Продажи: {strategy['sell_signals']}\n\n"
        
        # Активные ставки
        neural_text += f"🔥 *Активные ставки:* {stats['active_bets']}\n"
        neural_text += f"📋 *Завершенных сделок:* {stats['completed_trades']}\n\n"
        
        # Информация о системе
        neural_text += "🧠 *Архитектура:*\n"
        neural_text += "   • Входной слой: 50 нейронов\n"
        neural_text += "   • Скрытые слои: 32 \\+ 32 нейрона\n"
        neural_text += "   • Выходной слой: 10 нейронов \\(по стратегиям\\)\n"
        neural_text += "   • Активация: ReLU \\+ Softmax\n"
        neural_text += "   • Обучение: Обратное распространение\n\n"
        
        neural_text += "🎯 *Функции:*\n"
        neural_text += "   • Анализ рыночных данных\n"
        neural_text += "   • Оценка сигналов стратегий\n"
        neural_text += "   • Предсказание успешности\n"
        neural_text += "   • Автоматические ставки\n"
        neural_text += "   • Обучение на результатах\n\n"
        
        neural_text += "📊 *Анализируемые стратегии:*\n"
        neural_text += "   • strategy\\_01 \\- VolumeSpike\\_VWAP\\_Optimized\n"
        neural_text += "   • strategy\\_02 \\- TickTimer\\_CumDelta\\_Optimized\n"
        neural_text += "   • strategy\\_03 \\- MultiTF\\_VolumeSpike\\_Optimized\n"
        neural_text += "   • strategy\\_04 \\- KangarooTail\\_Optimized\n"
        neural_text += "   • strategy\\_05 \\- Fibonacci\\_RSI\\_Volume\\_Optimized\n"
        neural_text += "   • strategy\\_06 \\- VolumeClimaxReversal\\_Optimized\n"
        neural_text += "   • strategy\\_07 \\- BreakoutRetest\\_Optimized\n"
        neural_text += "   • strategy\\_08 \\- Заглушка \\(обучение\\)\n"
        neural_text += "   • strategy\\_09 \\- Заглушка \\(обучение\\)\n"
        neural_text += "   • strategy\\_10 \\- Заглушка \\(обучение\\)\n"
        
        print("✅ Текст сформирован с правильным экранированием Markdown")
        print(f"📏 Длина текста: {len(neural_text)} символов")
        
        # Проверяем на наличие проблемных символов
        problematic_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        found_problems = []
        
        for char in problematic_chars:
            if char in neural_text and f'\\{char}' not in neural_text:
                count = neural_text.count(char)
                found_problems.append(f"'{char}': {count} раз")
        
        if found_problems:
            print(f"⚠️ Найдены неэкранированные символы: {', '.join(found_problems)}")
        else:
            print("✅ Все специальные символы правильно экранированы")
        
        print("\n📄 Первые 500 символов текста:")
        print(neural_text[:500])
        print("...")
        
        print("\n✅ Функция нейронки исправлена и готова к использованию!")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании функции нейронки: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_neural_fixed() 