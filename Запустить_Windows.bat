@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Не удалось запустить программу. Нужен Python 3.10 или новее и интернет для первой установки зависимостей.
echo Скачать Python: https://www.python.org/downloads/
pause
exit /b 1
