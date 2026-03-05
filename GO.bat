@echo off
title Somon Market — Full Launch
cd /d "%~dp0"

echo ==================================
echo   SOMON MARKET — Starting...
echo ==================================
echo.

echo [1/3] Starting FastAPI on port 8000...
start "Somon FastAPI" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo [2/3] Starting ngrok tunnel (port 8000)...
start "Somon ngrok" cmd /k "ngrok http 8000"

timeout /t 4 /nobreak >nul

echo [3/3] Starting Telegram Bot...
start "Somon TG Bot" cmd /k ".venv\Scripts\python.exe bot.py"

echo.
echo ==================================
echo   All services launched!
echo.
echo   Site (local):  http://localhost:8000/web
echo   API docs:      http://localhost:8000/docs
echo   ngrok panel:   http://127.0.0.1:4040
echo.
echo   IMPORTANT: Copy ngrok HTTPS URL from
echo   ngrok window and update WEBAPP_URL in .env
echo   then restart the bot.
echo ==================================
echo.
pause >nul
