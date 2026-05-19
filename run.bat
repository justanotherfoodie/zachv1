@echo off
title Zach V1 - Glass Informatics Platform

echo.
echo  =============================================
echo   Zach V1 - Glass Informatics Platform
echo  =============================================
echo.

:: ── Check database ────────────────────────────────────────────
if not exist "data\sciglass_clean.db" (
    echo [ERROR] SciGlass database not found.
    echo         Please run setup.bat first.
    pause
    exit /b 1
)

:: ── Activate venv if present, otherwise use system Python ─────
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    set PYTHON=python
) else (
    set PYTHON=
    where py >nul 2>&1 && set PYTHON=py
    if "%PYTHON%"=="" where python >nul 2>&1 && set PYTHON=python
    if "%PYTHON%"=="" (
        echo [ERROR] Python not found. Run setup.bat first.
        pause
        exit /b 1
    )
)

echo [*] Using Python: %PYTHON%

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

:: ── Open browser after 3 s ────────────────────────────────────
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5050"

%PYTHON% app.py
pause
