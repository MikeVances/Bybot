# bot/core/interface.py
from abc import ABC, abstractmethod

class BotInterface(ABC):
    @abstractmethod
    def check_balance(self, symbol: str):
        pass
        
    @abstractmethod
    def run_strategy(self, strategy: str, risk: float):
        pass

# Реализации для CLI и Telegram будут наследовать этот класс