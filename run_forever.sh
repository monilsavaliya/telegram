#!/bin/bash
while true
do
    echo "🚀 Starting Jarvis..."
    python3.10 telegram_main.py
    echo "⚠️ Bot Crashed or Stopped. Restarting in 5 seconds..."
    sleep 5
done
