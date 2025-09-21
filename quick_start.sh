#!/bin/bash

# 🚀 BYBOT QUICK START - Быстрый запуск
# Для ежедневного использования

source .venv/bin/activate

echo "🚀 BYBOT Quick Start"
echo "===================="
echo
echo "1. Full System (main.py)"
echo "2. Enhanced Telegram Bot"
echo "3. Test All Strategies"
echo

read -p "Choice (1-3): " choice

case $choice in
    1)
        echo "🚀 Starting Full System..."
        python main.py
        ;;
    2)
        echo "🤖 Starting Enhanced Telegram Bot..."
        python run_enhanced_telegram_bot.py
        ;;
    3)
        echo "🧪 Running Tests..."
        python ../test_all_strategies.py
        ;;
    *)
        echo "❌ Invalid choice!"
        exit 1
        ;;
esac