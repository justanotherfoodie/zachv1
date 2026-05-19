@echo off
setlocal enabledelayedexpansion
title Zach V1 - Glass Informatics Platform

echo.
echo  =============================================
echo   Zach V1 - Glass Informatics Platform
echo  =============================================
echo.

:: ── Check database ────────────────────────────────────────────
if not exist "data\sciglass_clean.db" (
    echo [ERROR] SciGlass database not found.
    echo         Copy sciglass_clean.db into the data\ folder.
    pause
    exit /b 1
)

:: ── Find Python (check real install paths FIRST, skip Store stubs) ──
set PYTHON=

if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
    goto :found
)

:: Check real install locations before PATH (avoids Windows Store stub)
if exist "!LOCALAPPDATA!\Programs\Python\Python313\python.exe" (
    set PYTHON=!LOCALAPPDATA!\Programs\Python\Python313\python.exe
    goto :found
)
if exist "!LOCALAPPDATA!\Programs\Python\Python312\python.exe" (
    set PYTHON=!LOCALAPPDATA!\Programs\Python\Python312\python.exe
    goto :found
)
if exist "!LOCALAPPDATA!\Programs\Python\Python311\python.exe" (
    set PYTHON=!LOCALAPPDATA!\Programs\Python\Python311\python.exe
    goto :found
)
if exist "!LOCALAPPDATA!\Programs\Python\Python310\python.exe" (
    set PYTHON=!LOCALAPPDATA!\Programs\Python\Python310\python.exe
    goto :found
)
if exist "C:\Python313\python.exe" ( set PYTHON=C:\Python313\python.exe & goto :found )
if exist "C:\Python312\python.exe" ( set PYTHON=C:\Python312\python.exe & goto :found )
if exist "C:\Python311\python.exe" ( set PYTHON=C:\Python311\python.exe & goto :found )
if exist "C:\Python310\python.exe" ( set PYTHON=C:\Python310\python.exe & goto :found )

echo [ERROR] Python not found.
echo         Install Python 3.10+ from https://www.python.org/downloads/
echo         Check "Add Python to PATH" during install, then re-run this script.
pause
exit /b 1

:found
echo [*] Using Python: !PYTHON!

:: ── Install dependencies ──────────────────────────────────────
echo [*] Checking dependencies...
"!PYTHON!" -m pip install -r requirements.txt --quiet --disable-pip-version-check

if not exist "models_cache" mkdir models_cache

:: ── Free port 5050 ────────────────────────────────────────────
echo [*] Freeing port 5050...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5050 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo.
echo [*] Starting Zach V1 on http://localhost:5050
echo [*] Press Ctrl+C to stop.
echo.

start /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5050"

"!PYTHON!" app.py
pause
