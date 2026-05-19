@echo off
echo ============================================================
echo  Zach V1 — Setup
echo ============================================================
echo.

:: ── Python check ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

:: ── Virtual environment ───────────────────────────────────────
if not exist venv (
    echo [*] Creating virtual environment...
    python -m venv venv
)
echo [OK] Virtual environment ready

:: ── Install dependencies ──────────────────────────────────────
echo [*] Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
echo [OK] Dependencies installed

:: ── Download database ─────────────────────────────────────────
if exist data\sciglass_clean.db (
    echo [OK] Database already present — skipping download
) else (
    echo [*] Downloading SciGlass database (~300 MB)...
    echo     This may take a few minutes depending on your connection.
    curl -L --progress-bar -o data\sciglass_clean.db "https://github.com/gongyauc/zachv1/releases/download/v1.0/sciglass_clean.db"
    if errorlevel 1 (
        echo [ERROR] Download failed. Check your internet connection or download manually from:
        echo         https://github.com/gongyauc/zachv1/releases/tag/v1.0
        echo         and place sciglass_clean.db into the data\ folder.
        pause
        exit /b 1
    )
    echo [OK] Database downloaded
)

echo.
echo ============================================================
echo  Setup complete! Run the app with:  run.bat
echo ============================================================
echo.
pause
