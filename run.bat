@echo off
title Zach V1 - Glass Informatics Platform

echo.
echo  =============================================
echo   Zach V1 - Glass Informatics Platform
echo  =============================================
echo.

:: Locate Python (py launcher first, then python)
set PYTHON=
where py >nul 2>&1 && set PYTHON=py
if "%PYTHON%"=="" where python >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" where python3 >nul 2>&1 && set PYTHON=python3

if "%PYTHON%"=="" (
    echo [ERROR] Python not found.
    echo         Install Python 3.9+ from https://www.python.org/downloads/
    echo         Check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [*] Using: %PYTHON%
%PYTHON% --version

:: Install / update dependencies silently
echo [*] Checking dependencies...
%PYTHON% -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

:: Warn if SciGlass DB missing
if not exist "..\Zach 1.0\extracted\select\sciglass_clean.db" (
    echo.
    echo [WARNING] SciGlass database not found at:
    echo           ..\Zach 1.0\extracted\select\sciglass_clean.db
    echo.
)

if not exist "models_cache" mkdir models_cache

:: Free port 5050 if occupied (kills zombie processes from previous runs)
echo [*] Freeing port 5050...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5050 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo.
echo [*] Starting Zach V1 server on http://localhost:5050
echo [*] Press Ctrl+C to stop.
echo.

:: Open browser after 3-second delay (background)
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5050"

%PYTHON% app.py

pause
