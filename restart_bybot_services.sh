#!/bin/bash

# Перезапуск сервисов bybot-trading и bybot-telegram

sudo systemctl restart bybot-trading.service
sudo systemctl restart bybot-telegram.service

echo "Сервисы bybot-trading и bybot-telegram перезапущены." 