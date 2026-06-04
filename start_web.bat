@echo off
REM ============================================================
REM Meeting Processor - inicia frontend local no navegador
REM ============================================================

title Meeting Processor - Frontend

cd /d "%~dp0"

echo Iniciando frontend local em http://127.0.0.1:8765 ...
echo Pressione Ctrl+C para parar.
echo.

python -m meeting_processor web --port 8765
pause
