from setuptools import setup

setup(
    name="bybit_bot",
    version="0.1",
    py_modules=["bot"],
    install_requires=[
        "click>=8.0",
        "requests>=2.26",
    ],
    entry_points={
        "console_scripts": [
            "bybot = bot.cli:cli",
        ],
    },
)