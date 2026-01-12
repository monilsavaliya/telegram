@echo off
title Jarvis Bot - Auto Restart
color 0a

:start
cls
echo [LAUNCHER] Starting Jarvis Bot...
echo [LAUNCHER] Time: %time%
python telegram_main.py

echo.
echo [LAUNCHER] Bot Crashed or Stopped.
echo [LAUNCHER] Restarting in 3 seconds... (Press Ctrl+C to Stop)
alert
timeout /t 3
goto start
