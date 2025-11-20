@echo off
cd /d %~dp0
python -m venv venv
call venv\Scripts\activate.bat
if exist requirements.lock (
  pip install -r requirements.lock
) else (
  pip install -r requirements.txt
)
copy .env.example .env
echo Setup complete. Edit .env then run run.bat
pause