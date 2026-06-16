@echo off
cd /d C:\Users\Jorge\Superagente007

echo Iniciando Superagente007...

start "Agente - Superagente007" cmd /k "venv\Scripts\activate && python agent.py"
timeout /t 3 /nobreak > nul
start "Dashboard - Superagente007" cmd /k "venv\Scripts\activate && python dashboard/main.py"

timeout /t 3 /nobreak > nul
start "" "http://127.0.0.1:8080"
