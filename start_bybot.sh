#!/bin/bash

# 🚀 BYBOT LAUNCHER - Удобный запуск торговой системы
# Создано для простого управления всеми компонентами

set -e  # Выход при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Логотип
echo -e "${PURPLE}"
echo "╔═══════════════════════════════════════════════╗"
echo "║                   🚀 BYBOT 🚀                ║"
echo "║            Advanced Trading System            ║"
echo "╚═══════════════════════════════════════════════╝"
echo -e "${NC}"

# Проверка окружения
echo -e "${CYAN}🔍 Проверка окружения...${NC}"

# Проверка виртуального окружения
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo -e "${GREEN}✅ Virtual environment активирован: $(basename $VIRTUAL_ENV)${NC}"
else
    echo -e "${YELLOW}⚠️  Активирую virtual environment...${NC}"
    source .venv/bin/activate
    echo -e "${GREEN}✅ Virtual environment активирован${NC}"
fi

# Проверка зависимостей
echo -e "${CYAN}📦 Проверка зависимостей...${NC}"
python -c "import numpy, pandas, ta, psutil, telegram" 2>/dev/null && echo -e "${GREEN}✅ Все зависимости установлены${NC}" || {
    echo -e "${RED}❌ Отсутствуют зависимости! Устанавливаю...${NC}"
    pip install -r requirements.txt
}

# Меню выбора режима запуска
echo
echo -e "${BLUE}🎯 Выберите режим:${NC}"
echo "1. 🚀 Быстрый запуск (Full System)"
echo "2. ℹ️  Статус системы"
echo "3. 🧪 Тест отправки Telegram"
echo "4. 🛑 Остановить фоновые процессы"
echo "5. 📋 Подробное меню"
echo

read -p "Ваш выбор (1-5): " choice

case $choice in
    1)
        echo -e "${GREEN}🚀 Быстрый запуск полной системы...${NC}"
        echo -e "${YELLOW}💡 Торговля + Telegram бот интегрированы${NC}"
        python main.py
        ;;
    2)
        echo -e "${CYAN}ℹ️  Статус системы...${NC}"
        echo
        echo -e "${YELLOW}📊 Активные стратегии:${NC}"
        python -c "
from bot.core.trader import get_active_strategies
from config import get_strategy_config
strategies = get_active_strategies()
print(f'Найдено: {len(strategies)} активных стратегий')
for s in strategies:
    config = get_strategy_config(s)
    print(f'  • {s}: \${config[\"trade_amount\"]}')
"
        echo
        echo -e "${YELLOW}🤖 Telegram бот:${NC}"
        python -c "
from config import TELEGRAM_TOKEN, ADMIN_CHAT_ID
print(f'Token: {TELEGRAM_TOKEN[:10] if TELEGRAM_TOKEN else \"None\"}...')
print(f'Admin ID: {ADMIN_CHAT_ID if ADMIN_CHAT_ID else \"None\"}')
"
        echo
        echo -e "${YELLOW}💰 Балансы:${NC}"
        python -c "
from bot.exchange.bybit_api_v5 import TradingBotV5
from config import get_strategy_config
try:
    config = get_strategy_config('volume_vwap_default')
    api = TradingBotV5('BTCUSDT', config['api_key'], config['api_secret'], config['uid'])
    balance = api.get_wallet_balance_v5()
    if balance and balance.get('retCode') == 0:
        usdt = balance['result']['list'][0]['coin'][0]
        print(f'Основной счет: \${float(usdt[\"walletBalance\"]):.2f}')
    else:
        print('API недоступен (нормально для demo)')
except Exception as e:
    print(f'Ошибка получения баланса: {str(e)[:50]}...')
"
        ;;
    3)
        echo -e "${CYAN}🧪 Отправляю тестовое сообщение в Telegram...${NC}"
        if [[ -f "send_test_message.py" ]]; then
            python send_test_message.py || echo -e "${YELLOW}⚠️  Не удалось отправить сообщение (проверьте токен).${NC}"
        else
            echo -e "${YELLOW}⚠️  Скрипт send_test_message.py не найден.${NC}"
        fi
        ;;
    4)
        echo -e "${RED}🛑 Останавливаю фоновые процессы...${NC}"

        if command -v systemctl >/dev/null 2>&1; then
            echo "Пробую остановить systemd сервисы..."
            sudo systemctl stop bybot-trading.service 2>/dev/null || echo "bybot-trading не запущен"
            sudo systemctl stop bybot-telegram.service 2>/dev/null || echo "bybot-telegram не запущен"
        else
            echo -e "${YELLOW}⚠️  systemctl недоступен — пропускаю остановку сервисов.${NC}"
        fi

        echo "Завершаю процессы Python..."
        pkill -f "python.*main.py" 2>/dev/null || echo "main.py не запущен"
        pkill -f "python.*bot.core.trader" 2>/dev/null || echo "bot.core.trader не запущен"
        pkill -f "python.*metrics_exporter" 2>/dev/null || echo "metrics_exporter не запущен"

        echo -e "${GREEN}✅ Обработка завершена${NC}"
        ;;
    5)
        echo -e "${PURPLE}📋 Подробное меню (будущая функция)${NC}"
        echo "В разработке: расширенные опции конфигурации"
        ;;
    *)
        echo -e "${RED}❌ Неверный выбор!${NC}"
        exit 1
        ;;
esac

echo
echo -e "${GREEN}🎉 Готово!${NC}"
