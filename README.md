# Zach V1 — Glass Informatics Platform

A free, open-source glass informatics tool for researchers and engineers. Runs entirely on your local machine — no data is ever transmitted or shared.

## Features

- **Explore Database** — search and filter 400 000+ glasses from the SciGlass dataset by composition, property, and oxide system
- **ML Property Prediction** — Random Forest models trained on SciGlass; predict density, Tg, CTE, refractive index, and liquidus temperature
- **Batch CSV Prediction** — upload a spreadsheet of compositions, download predictions in seconds
- **Ternary Diagram** — interactive Plotly ternary plot coloured by any property
- **Scatter & Histogram** — composition–property scatter plots, property distributions, and pairwise correlation matrix
- **Similarity Search** — nearest-neighbour search to find the most compositionally similar glasses in the database
- **Viscosity Fitting** — fit MYEGA / VFT / Avramov-Milchev models to measured viscosity data
- **Inverse Design** — Latin Hypercube Sampling + Genetic Algorithm optimisation toward target properties
- **Theory Tools** — NBO/T, optical basicity (Duffy-Ingram), topological constraints (Phillips-Thorpe)
- **Add Glass / CSV Import** — build and manage your own private glass library; bulk-import from CSV
- **Database Management** — export/import your private library as JSON or SQLite; all data stays local

## Requirements

- Python 3.10+
- The `sciglass_clean.db` database file (see below)

## Installation

```bash
git clone https://github.com/gongyauc/zachv1.git
cd zachv1
pip install -r requirements.txt
```

## Database Setup

The SciGlass database file (`sciglass_clean.db`) is not included in this repository due to its size.

**Download:** [sciglass_clean.db — Google Drive](#) *(link coming soon)*

Once downloaded, either:

**Option A** — place it at the default path the app expects:
```
../Zach 1.0/extracted/select/sciglass_clean.db
```

**Option B** — set an environment variable pointing to wherever you saved it:
```bash
# Windows
set SCIGLASS_DB=C:\path\to\sciglass_clean.db

# macOS / Linux
export SCIGLASS_DB=/path/to/sciglass_clean.db
```

## Running

**Windows:**
```
run.bat
```

**macOS / Linux:**
```bash
python app.py
```

Then open [http://localhost:5050](http://localhost:5050) in your browser.

## Privacy

Zach V1 runs 100% locally. No composition data, no glass library entries, and no usage data is ever sent anywhere. Your research stays on your machine.

## Testing Services

The development of Zach V1 is partially funded by contracted glass testing services. If you find this tool useful, consider engaging our lab for:

- Glass melting (contracted)
- Glass machining
- Composition analysis — ICP-OES
- DSC-TGA analysis
- Thermal-mechanical testing
- UV-Vis-IR spectroscopy

Contact: [gongyauc@gmail.com](mailto:gongyauc@gmail.com)

## Data Source

The SciGlass database is used under the [Open Database License (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/1-0/). Any derivative databases must be shared under the same license.

## License

MIT License — see `LICENSE` for details.
