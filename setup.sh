#!/usr/bin/env bash
set -e

echo "============================================================"
echo " Zach V1 — Setup"
echo "============================================================"
echo

# ── Python check ──────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Install it from https://python.org"
    exit 1
fi
echo "[OK] $(python3 --version) found"

# ── Virtual environment ───────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv venv
fi
echo "[OK] Virtual environment ready"

# ── Install dependencies ──────────────────────────────────────
echo "[*] Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet
echo "[OK] Dependencies installed"

# ── Download database ─────────────────────────────────────────
if [ -f "data/sciglass_clean.db" ]; then
    echo "[OK] Database already present — skipping download"
else
    echo "[*] Downloading SciGlass database (~300 MB)..."
    echo "    This may take a few minutes depending on your connection."
    curl -L --progress-bar -o data/sciglass_clean.db \
        "https://github.com/gongyauc/zachv1/releases/download/v1.0/sciglass_clean.db"
    echo "[OK] Database downloaded"
fi

echo
echo "============================================================"
echo " Setup complete!"
echo " Run the app with:  source venv/bin/activate && python app.py"
echo " Then open:         http://localhost:5050"
echo "============================================================"
echo
