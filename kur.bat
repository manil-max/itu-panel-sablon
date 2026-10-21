@echo off
rem ITU Panel kurulumu: cift tikla. Python yoksa kurar, paketleri kurar, src\kurulum.py'yi calistirir.
rem Tek bir adim icin: kur.bat --whatsapp   (ya da --bildirim, --drive, --durum ...)
chcp 65001 >nul
cd /d "%~dp0"
title ITU Panel kurulumu
if exist ".venv\Scripts\python.exe" goto paketler

echo [1/3] Python araniyor...
set "BASE="
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "BASE=%%i"
if not defined BASE for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "BASE=%%i"
if defined BASE "%BASE%" -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul || set "BASE="
if not defined BASE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "BASE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined BASE (
  echo Python bulunamadi. Kuruluyor (winget, 1-2 dakika^)...
  winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "BASE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined BASE (
  echo.
  echo Python kurulamadi. https://www.python.org/downloads/ adresinden Python indirip kur,
  echo kurarken "Add python.exe to PATH" kutusunu isaretle, sonra kur.bat'a tekrar cift tikla.
  pause
  exit /b 1
)
echo [2/3] Sanal ortam olusturuluyor...
"%BASE%" -m venv .venv
if errorlevel 1 (
  echo Sanal ortam olusturulamadi.
  pause
  exit /b 1
)

:paketler
echo [3/3] Paketler kontrol ediliyor...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Paketler kurulamadi. Internet baglantini kontrol edip tekrar dene.
  pause
  exit /b 1
)
set "PYTHONIOENCODING=utf-8"
".venv\Scripts\python.exe" src\kurulum.py %*
echo.
pause
