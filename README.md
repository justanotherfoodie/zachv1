# Zach V1 — Glass Informatics Platform

A free, open-source glass informatics tool for researchers and engineers. Runs entirely on your local machine — no data is ever transmitted or shared.

---

## Quick Start

### Windows

```
1. Download and unzip this repository
2. Double-click  setup.bat       ← installs Python packages + downloads the database (~300 MB)
3. Double-click  run.bat         ← starts the app and opens your browser
```

### macOS / Linux

```bash
git clone https://github.com/gongyauc/zachv1.git
cd zachv1
chmod +x setup.sh && ./setup.sh        # installs packages + downloads the database
source venv/bin/activate && python app.py
```

Then open **http://localhost:5050** in your browser.

---

## Requirements

- Python 3.10 or newer — download from https://python.org
- Internet connection for the one-time database download (~300 MB)

No other installation needed. `setup.bat` / `setup.sh` handles everything.

---

## Features

| Feature | Description |
|---|---|
| **Explore Database** | Search 400 000+ glasses from SciGlass by composition, property, and oxide system |
| **ML Prediction** | Predict density, Tg, CTE, refractive index, liquidus temperature |
| **Batch CSV Predict** | Upload a spreadsheet of compositions, download predictions instantly |
| **Ternary Diagram** | Interactive ternary plot coloured by any property |
| **Scatter & Histogram** | Composition–property scatter, property distributions, correlation matrix |
| **Similarity Search** | Find the most compositionally similar glasses in the database |
| **Viscosity Fitting** | Fit MYEGA / VFT / Avramov-Milchev models to measured data |
| **Inverse Design** | Optimise composition toward target properties (LHS + Genetic Algorithm) |
| **Theory Tools** | NBO/T, optical basicity, topological constraints |
| **Private Glass Library** | Add and manage your own glasses; bulk-import via CSV |
| **Database Backup** | Export / import your private library as JSON or SQLite |

---

## Privacy

Zach V1 runs 100% locally. No composition data, no glass library entries, and no usage information is ever sent anywhere. Your research stays on your machine.

---

## Testing Services

Zach V1 is free and open. Contracted testing work partially funds its ongoing maintenance and development. If you find this tool useful in your research, consider engaging our lab:

- Glass melting (contracted)
- Glass machining
- Composition analysis — ICP-OES
- DSC-TGA analysis
- Thermal-mechanical testing
- UV-Vis-IR spectroscopy

**Contact:** gongyauc@gmail.com

---

## Data Source

The SciGlass database is used under the [Open Database License (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/1-0/). Derivative databases must be shared under the same license.

## License

MIT — see `LICENSE` for details.
