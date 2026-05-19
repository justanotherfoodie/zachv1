import os

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))

# ── Database paths ────────────────────────────────────────────────────────────
# Set SCIGLASS_DB env variable to point to your sciglass_clean.db file,
# or place sciglass_clean.db in the same directory as this file.
# Download link: see README.md
_default_db = os.path.join(BASE_DIR, "data", "sciglass_clean.db")
DB_PATH    = os.environ.get("SCIGLASS_DB", _default_db)
USER_DB    = os.path.join(BASE_DIR, "user_data.db")
MODEL_DIR  = os.path.join(BASE_DIR, "models_cache")

# Key oxide list used as ML features (ordered, matches IUPAC / SciGlass convention)
OXIDES = [
    "SiO2","B2O3","Al2O3","P2O5","GeO2","TeO2",
    "Na2O","K2O","Li2O","Cs2O","Rb2O",
    "CaO","MgO","BaO","SrO","ZnO","PbO","CdO","BeO",
    "TiO2","ZrO2","HfO2","La2O3","Gd2O3","Y2O3",
    "Fe2O3","Nb2O5","Ta2O5","WO3","MoO3","V2O5",
    "Bi2O3","Sb2O3","As2O3",
    "F","Cl","Se","S",
]

# Viscosity reference points (log Pa·s)
VISC_REF = {
    "melting":   1.0,
    "working":   4.0,
    "softening": 6.6,
    "annealing": 12.0,
    "strain":    13.5,
}

# Optical basicity values (Duffy-Ingram)
OPTICAL_BASICITY = {
    "SiO2":  0.48, "B2O3":  0.42, "Al2O3": 0.60, "P2O5":  0.40,
    "GeO2":  0.48, "TeO2":  0.82, "Na2O":  1.15, "K2O":   1.40,
    "Li2O":  1.00, "CaO":   1.00, "MgO":   0.78, "BaO":   1.15,
    "SrO":   1.10, "ZnO":   0.82, "PbO":   0.90, "TiO2":  0.65,
    "ZrO2":  0.68, "La2O3": 1.13, "Fe2O3": 0.75, "Bi2O3": 0.99,
    "Y2O3":  1.00, "CeO2":  0.90, "Nb2O5": 0.65, "Ta2O5": 0.60,
    "Gd2O3": 1.10, "Nd2O3": 1.12, "BaO":   1.15,
}

# Coordination numbers for NBO/T and constraint theory
COORD = {
    # (cation CN, O per formula unit, valence)
    "Si":  (4, 2, 4), "B":   (3, 1.5, 3), "Al":  (4, 1.5, 3),
    "P":   (4, 2.5, 5), "Ge":  (4, 2, 4), "Te":  (4, 2, 4),
    "Na":  (6, 0.5, 1), "K":   (8, 0.5, 1), "Li":  (4, 0.5, 1),
    "Ca":  (6, 1,   2), "Mg":  (6, 1,   2), "Ba":  (8, 1,   2),
    "Sr":  (8, 1,   2), "Zn":  (4, 1,   2), "Pb":  (4, 1,   2),
    "Ti":  (6, 2,   4), "Zr":  (8, 2,   4), "La":  (9, 1.5, 3),
    "Fe":  (4, 1.5, 3), "Bi":  (3, 1.5, 3), "Nb":  (6, 2.5, 5),
}

SECRET_KEY = "zachglassapp2025"
DEBUG      = True
PORT       = 5050
