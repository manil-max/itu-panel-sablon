@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY goto kur
goto calistir

:kur
echo Ilk calistirma: Python sanal ortami kuruluyor (bir kere)...
python -m venv .venv
if errorlevel 1 (
  echo Python bulunamadi. python.org'dan Python kurup tekrar dene.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -q -r requirements.txt
set "PY=.venv\Scripts\python.exe"

:calistir
"%PY%" sunucu.py
pause
