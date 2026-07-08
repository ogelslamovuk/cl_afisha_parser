@echo off
cd /d "%~dp0"

if not exist logs mkdir logs

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "main.py" >> "logs\task_scheduler.log" 2>&1
) else (
    python "main.py" >> "logs\task_scheduler.log" 2>&1
)

exit /b %ERRORLEVEL%
