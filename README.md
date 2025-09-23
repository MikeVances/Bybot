# Bybot
Описание проекта, как запускать и конфигурировать.

## Quickstart
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## Запуск
- `python main.py` — полный старт торговой системы (Telegram, торговый цикл, мониторинг).
- При импорте модуля `main` (например, `from main import StrategyManager`) торговый цикл **не** запускается автоматически. Это облегчает локальное тестирование: запускайте `main.main()` вручную, когда нужно поднять всю систему.
