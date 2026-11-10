@echo off
timeout /t 30 /nobreak >nul
cd /d "%~dp0"
python k90_sync.py