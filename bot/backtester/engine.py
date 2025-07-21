import pandas as pd

class BacktestEngine:
    def __init__(self, strategy, data):
        self.strategy = strategy
        self.data = data
        self.results = None

    def run(self):
        self.results = self.strategy(self.data)
        return self.results 