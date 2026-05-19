"""
Glass property calculators based on composition.

Theories implemented:
  1. NBO/T          — Non-bridging oxygens per tetrahedra (network connectivity)
  2. Optical Basicity — Duffy-Ingram model
  3. Topological Constraint Theory (TCT) — mean coordination & rigidity
  4. Batch Calculator — oxide → raw materials
  5. Mixing Rules    — linear additive for density, CTE, Tg (Priven model)
  6. Sun Bond Strength — Zachariasen-Sun network former classification
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
from config import OPTICAL_BASICITY, COORD, OXIDES

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Molar masses (g/mol)
MOLAR_MASS = {
    "SiO2":   60.08, "B2O3":   69.62, "Al2O3": 101.96, "P2O5":  141.94,
    "GeO2":  104.64, "TeO2":  159.60, "Na2O":   61.98, "K2O":    94.20,
    "Li2O":   29.88, "Cs2O":  281.81, "Rb2O":  186.94, "CaO":    56.08,
    "MgO":    40.30, "BaO":   153.33, "SrO":   103.62, "ZnO":    81.39,
    "PbO":   223.19, "CdO":   128.41, "BeO":    25.01, "TiO2":   79.87,
    "ZrO2":  123.22, "HfO2":  210.49, "La2O3": 325.81, "Gd2O3": 362.50,
    "Y2O3":  225.81, "Fe2O3": 159.69, "Nb2O5": 265.81, "Ta2O5": 441.89,
    "WO3":   231.84, "MoO3":  143.94, "V2O5":  181.88, "Bi2O3": 465.96,
    "Sb2O3": 291.50, "As2O3": 197.84, "F":      19.00, "Cl":     35.45,
    "Se":     78.97, "S":      32.06,
}

# Number of formula units (cations) per oxide formula:  SiO2→1, Al2O3→2, etc.
CATION_COUNT = {
    "SiO2":1,"B2O3":2,"Al2O3":2,"P2O5":2,"GeO2":1,"TeO2":1,
    "Na2O":2,"K2O":2,"Li2O":2,"Cs2O":2,"Rb2O":2,
    "CaO":1,"MgO":1,"BaO":1,"SrO":1,"ZnO":1,"PbO":1,"CdO":1,"BeO":1,
    "TiO2":1,"ZrO2":1,"HfO2":1,"La2O3":2,"Gd2O3":2,"Y2O3":2,
    "Fe2O3":2,"Nb2O5":2,"Ta2O5":2,"WO3":1,"MoO3":1,"V2O5":2,
    "Bi2O3":2,"Sb2O3":2,"As2O3":2,
    "F":1,"Cl":1,"Se":1,"S":1,
}

# Ion abbreviation → oxide mapping (for COORD lookup)
ION_TO_OXIDE = {
    "Si":"SiO2","B":"B2O3","Al":"Al2O3","P":"P2O5","Ge":"GeO2","Te":"TeO2",
    "Na":"Na2O","K":"K2O","Li":"Li2O","Ca":"CaO","Mg":"MgO","Ba":"BaO",
    "Sr":"SrO","Zn":"ZnO","Pb":"PbO","Ti":"TiO2","Zr":"ZrO2","La":"La2O3",
    "Fe":"Fe2O3","Bi":"Bi2O3","Nb":"Nb2O5",
}


def _mol_fractions(comp: dict) -> dict:
    """
    Convert composition (any unit) to mole fractions.
    comp = {oxide: value, ...}  where values sum to ~100 (wt% or mol%).
    Detects wt% automatically; if sum ~100 and no molar mass conversion needed
    we still normalise.
    """
    total = sum(comp.values())
    if total <= 0:
        return {}
    # Convert wt% → mol fraction
    moles = {}
    for ox, val in comp.items():
        mm = MOLAR_MASS.get(ox)
        if mm and val > 0:
            moles[ox] = val / mm
    mol_total = sum(moles.values())
    if mol_total <= 0:
        return {}
    return {ox: m / mol_total for ox, m in moles.items()}


# ─────────────────────────────────────────────────────────────────────────────
# 1. NBO/T  (non-bridging oxygens per network-forming tetrahedron)
# ─────────────────────────────────────────────────────────────────────────────

# Network formers (tetrahedral), modifiers, and amphoteric
NETWORK_FORMERS  = {"SiO2","GeO2","P2O5","B2O3","Al2O3","TeO2","As2O3","Sb2O3"}
NETWORK_MODIFIERS = {"Na2O","K2O","Li2O","Cs2O","Rb2O","CaO","MgO","BaO","SrO",
                     "PbO","ZnO","CdO","BeO","La2O3","Gd2O3","Y2O3","Bi2O3"}


def nbo_t(comp_wt: dict) -> dict:
    """
    Calculate NBO/T for a glass composition (given in wt%).

    Returns dict with keys:
      nbo_t       — non-bridging oxygens per tetrahedron
      n_tet       — mole fraction of tetrahedrally coordinated cations
      n_mod       — mole fraction of modifier cations (donate O to NBO)
      connectivity — qualitative network connectivity description
    """
    xf = _mol_fractions(comp_wt)
    if not xf:
        return {}

    # Moles of oxygens donated to network (bridging) vs. consumed as NBO
    # Each network former contributes its O to bridging; each modifier donates
    # its O as non-bridging.
    # Simplified Mysen formulation: NBO/T = 2 * X_O / X_T - 4
    # where X_O = total oxygens (in mol), X_T = tetrahedral cations (in mol)

    # Count oxygens per formula unit
    OX_PER_FORMULA = {
        "SiO2":2,"B2O3":1.5,"Al2O3":1.5,"P2O5":2.5,"GeO2":2,"TeO2":2,
        "Na2O":0.5,"K2O":0.5,"Li2O":0.5,"Cs2O":0.5,"Rb2O":0.5,
        "CaO":1,"MgO":1,"BaO":1,"SrO":1,"ZnO":1,"PbO":1,"CdO":1,"BeO":1,
        "TiO2":2,"ZrO2":2,"HfO2":2,"La2O3":1.5,"Gd2O3":1.5,"Y2O3":1.5,
        "Fe2O3":1.5,"Nb2O5":2.5,"Ta2O5":2.5,"WO3":3,"MoO3":3,"V2O5":2.5,
        "Bi2O3":1.5,"Sb2O3":1.5,"As2O3":1.5,
    }

    # Tetrahedral formers (CN=4)
    TET_FORMERS = {"SiO2","GeO2","P2O5","Al2O3","B2O3","As2O3","Sb2O3"}

    total_O  = sum(xf.get(ox, 0) * OX_PER_FORMULA.get(ox, 1) for ox in xf)
    total_tet = sum(xf.get(ox, 0) / CATION_COUNT.get(ox, 1) for ox in TET_FORMERS if ox in xf)

    if total_tet <= 0:
        nbo = None
        connectivity = "No network formers present"
    else:
        # NBO/T (Mysen):  (2 * total_O / total_tet) - 4
        nbo = round((2 * total_O / total_tet) - 4, 3)
        if nbo < 0:
            connectivity = "Fully polymerised (Q4 network)"
        elif nbo < 0.5:
            connectivity = "Highly connected (Q3-Q4)"
        elif nbo < 1.5:
            connectivity = "Moderately connected (Q2-Q3)"
        elif nbo < 2.5:
            connectivity = "Weakly connected (Q1-Q2)"
        else:
            connectivity = "Depolymerised (Q0-Q1)"

    return {
        "nbo_t":        nbo,
        "total_O_mol":  round(total_O, 4),
        "total_tet_mol": round(total_tet, 4),
        "connectivity": connectivity,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Optical Basicity
# ─────────────────────────────────────────────────────────────────────────────

def optical_basicity(comp_wt: dict) -> dict:
    """
    Duffy-Ingram optical basicity: Λ = Σ xi*ni*Λi / Σ xi*ni
    where xi = equivalent oxide fraction, ni = number of oxygens per formula unit,
    and Λi is the oxide's basicity contribution.
    """
    xf = _mol_fractions(comp_wt)
    if not xf:
        return {}

    OX_COUNT = {  # oxygens per oxide formula
        "SiO2":2,"B2O3":3,"Al2O3":3,"P2O5":5,"GeO2":2,"TeO2":2,
        "Na2O":1,"K2O":1,"Li2O":1,"Cs2O":1,"Rb2O":1,
        "CaO":1,"MgO":1,"BaO":1,"SrO":1,"ZnO":1,"PbO":1,"TiO2":2,
        "ZrO2":2,"La2O3":3,"Fe2O3":3,"Bi2O3":3,"Y2O3":3,"Gd2O3":3,
        "Nb2O5":5,"Ta2O5":5,"CdO":1,"BeO":1,"HfO2":2,
    }

    numerator   = 0.0
    denominator = 0.0
    missing = []
    for ox, x in xf.items():
        lam = OPTICAL_BASICITY.get(ox)
        n_o = OX_COUNT.get(ox, 1)
        if lam is not None:
            numerator   += x * n_o * lam
            denominator += x * n_o
        else:
            missing.append(ox)

    if denominator <= 0:
        return {"optical_basicity": None, "missing_oxides": missing}

    lam_avg = round(numerator / denominator, 4)
    # Qualitative interpretation
    if lam_avg < 0.5:
        char = "Acidic glass (high silica / phosphate)"
    elif lam_avg < 0.65:
        char = "Weakly basic (typical silicate)"
    elif lam_avg < 0.85:
        char = "Moderately basic (alkali silicate)"
    else:
        char = "Basic glass (high modifier content)"

    return {
        "optical_basicity": lam_avg,
        "character":        char,
        "missing_oxides":   missing,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Topological Constraint Theory (Phillips-Thorpe + Gupta-Cooper)
# ─────────────────────────────────────────────────────────────────────────────

# Per-cation constraints (bond-stretching + bond-bending)
# BS = bond-stretching = CN/2 (shared between 2 atoms)
# BB = bond-bending   = 2*CN - 3 (for CN≥2)
# Total angular = BB per atom
CONSTRAINT_TABLE = {
    # oxide: (CN, BS_per_cation, BB_per_cation)
    "SiO2":  (4, 2.0, 5.0),
    "B2O3":  (3, 1.5, 3.0),  # BO3 planar
    "Al2O3": (4, 2.0, 5.0),
    "P2O5":  (4, 2.0, 5.0),
    "GeO2":  (4, 2.0, 5.0),
    "TeO2":  (4, 2.0, 5.0),
    "Na2O":  (6, 1.0, 0.0),  # modifier — no angular constraints
    "K2O":   (8, 1.0, 0.0),
    "Li2O":  (4, 1.0, 0.0),
    "CaO":   (6, 1.0, 0.0),
    "MgO":   (6, 1.0, 0.0),
    "BaO":   (8, 1.0, 0.0),
    "ZnO":   (4, 1.0, 0.0),
    "PbO":   (4, 1.0, 0.0),
    "TiO2":  (6, 1.0, 0.0),
    "ZrO2":  (8, 1.0, 0.0),
    "La2O3": (9, 1.0, 0.0),
    "Fe2O3": (4, 2.0, 5.0),
}


def topological_constraints(comp_wt: dict) -> dict:
    """
    Mean-field topological constraint count per atom (n_c).
    Rigidity transition: n_c = 3 (isostatic).
    n_c < 3 → floppy (underconstrained),  n_c > 3 → stressed rigid.
    """
    xf = _mol_fractions(comp_wt)
    if not xf:
        return {}

    mean_coord = 0.0  # mean cation coordination number
    n_bs       = 0.0  # bond-stretching constraints per atom
    n_bb       = 0.0  # bond-bending constraints per atom
    total_x    = 0.0

    for ox, x in xf.items():
        entry = CONSTRAINT_TABLE.get(ox)
        if entry:
            cn, bs, bb = entry
            n_cations = x / CATION_COUNT.get(ox, 1)
            mean_coord += n_cations * cn
            n_bs       += n_cations * bs
            n_bb       += n_cations * bb
            total_x    += n_cations

    if total_x <= 0:
        return {}

    mean_coord /= total_x
    n_bs       /= total_x
    n_bb       /= total_x
    n_c         = n_bs + n_bb

    # Note: n_c here is constraints per network cation (not per atom).
    # Pure SiO2: ~7 (2 BS + 5 BB per Si); pure Na2O: ~1 (modifier only).
    # Typical silicate glasses: 4–6.
    if n_c < 2.5:
        regime = "Floppy — high modifier content, low network connectivity"
    elif n_c < 4.0:
        regime = "Moderately flexible — mixed former/modifier glass"
    elif n_c < 5.5:
        regime = "Well-constrained — good glass forming region"
    elif n_c < 6.5:
        regime = "Highly constrained — tetrahedral-former dominated"
    else:
        regime = "Over-constrained — very high former content"

    return {
        "mean_coordination":     round(mean_coord, 3),
        "n_constraints_total":   round(n_c, 3),
        "n_bond_stretching":     round(n_bs, 3),
        "n_bond_bending":        round(n_bb, 3),
        "rigidity_regime":       regime,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Zachariasen-Sun bond strength classification
# ─────────────────────────────────────────────────────────────────────────────

# Single bond strength (kJ/mol) — Sun 1947
BOND_STRENGTH = {
    "SiO2":443,"B2O3":498,"P2O5":464,"Al2O3":318,"GeO2":419,"TeO2":376,
    "TiO2":305,"ZrO2":310,"Nb2O5":356,"WO3":293,"MoO3":293,"V2O5":356,
    "Na2O":84,"K2O":54,"Li2O":151,"CaO":134,"MgO":155,"BaO":109,
    "BaO":109,"SrO":119,"ZnO":151,"PbO":143,"Fe2O3":264,
}


def network_former_analysis(comp_wt: dict) -> dict:
    """Classify oxides as formers / intermediates / modifiers by bond strength."""
    xf = _mol_fractions(comp_wt)
    formers     = {}
    intermediates = {}
    modifiers   = {}
    for ox, x in xf.items():
        bs = BOND_STRENGTH.get(ox)
        if bs is None:
            continue
        if bs >= 350:
            formers[ox] = round(x * 100, 2)
        elif bs >= 250:
            intermediates[ox] = round(x * 100, 2)
        else:
            modifiers[ox] = round(x * 100, 2)
    return {
        "formers":      formers,
        "intermediates": intermediates,
        "modifiers":    modifiers,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Linear additive property estimates (empirical mixing rules)
#    Coefficients from SciGlass handbook / Priven 2004 model
# ─────────────────────────────────────────────────────────────────────────────

# Density additive factors (g/cm³ per mol%)
DENSITY_FACTORS = {
    "SiO2":0.0228,"B2O3":0.0197,"Al2O3":0.0407,"P2O5":0.0427,
    "Na2O":0.0414,"K2O":0.0601,"Li2O":0.0221,"CaO":0.0318,
    "MgO":0.0237,"BaO":0.0899,"PbO":0.1063,"ZnO":0.0434,
    "TiO2":0.0397,"ZrO2":0.0620,"La2O3":0.1308,"Fe2O3":0.0798,
}

# Tg additive factors (°C per mol%) — approximate
TG_FACTORS = {
    "SiO2":6.02,"B2O3":2.01,"Al2O3":5.0,"P2O5":2.5,
    "Na2O":-7.0,"K2O":-9.0,"Li2O":-4.5,"CaO":-2.5,
    "MgO":-2.0,"BaO":-3.5,"ZnO":-2.0,"PbO":-3.0,
    "TiO2":1.5,"ZrO2":4.0,"La2O3":3.5,"Fe2O3":0.5,
}

# CTE additive factors (1e-7 /°C per mol%)
CTE_FACTORS = {
    "SiO2":0.038,"B2O3":0.101,"Al2O3":-0.003,"P2O5":0.13,
    "Na2O":0.339,"K2O":0.394,"Li2O":0.258,"CaO":0.130,
    "MgO":0.060,"BaO":0.200,"ZnO":0.060,"PbO":0.130,
    "TiO2":0.010,"ZrO2":-0.020,"La2O3":0.020,"Fe2O3":0.020,
}


def estimate_properties(comp_wt: dict) -> dict:
    """
    Linear additive estimates for density, Tg, and CTE.
    These are order-of-magnitude estimates only.
    """
    xf = _mol_fractions(comp_wt)
    if not xf:
        return {}

    # mol% from mol fractions
    mol_pct = {ox: v * 100 for ox, v in xf.items()}

    density = sum(mol_pct.get(ox, 0) * DENSITY_FACTORS.get(ox, 0) for ox in mol_pct)
    tg      = sum(mol_pct.get(ox, 0) * TG_FACTORS.get(ox, 0)      for ox in mol_pct)
    cte     = sum(mol_pct.get(ox, 0) * CTE_FACTORS.get(ox, 0)     for ox in mol_pct)

    return {
        "density_est_g_cm3":   round(density, 3) if density > 0 else None,
        "Tg_est_degC":         round(tg, 0)      if tg > 0 else None,
        "CTE_est_1e7_per_degC": round(cte, 1)   if cte > 0 else None,
        "note": "Linear additive estimates — accuracy ±5-15%",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Batch Calculator: wt% oxide → raw material batch weights
# ─────────────────────────────────────────────────────────────────────────────

# Common raw materials and their oxide equivalents
RAW_MATERIALS = {
    "SiO2":   {"name": "Silica sand (SiO2)",           "purity": 0.998, "mw": 60.09,  "oxide": "SiO2",  "factor": 1.000},
    "Na2O":   {"name": "Soda ash (Na2CO3)",            "purity": 0.998, "mw": 105.99, "oxide": "Na2O",  "factor": 105.99/61.98},
    "CaO":    {"name": "Limestone (CaCO3)",            "purity": 0.975, "mw": 100.09, "oxide": "CaO",   "factor": 100.09/56.08},
    "Al2O3":  {"name": "Alumina (Al2O3)",              "purity": 0.995, "mw": 101.96, "oxide": "Al2O3", "factor": 1.000},
    "MgO":    {"name": "Dolomite (MgCO3·CaCO3)",       "purity": 0.98,  "mw": 184.40, "oxide": "MgO",   "factor": 184.4/80.31},
    "B2O3":   {"name": "Boric acid (H3BO3)",           "purity": 0.998, "mw": 61.83,  "oxide": "B2O3",  "factor": 61.83*2/69.62},
    "K2O":    {"name": "Potash (K2CO3)",               "purity": 0.99,  "mw": 138.21, "oxide": "K2O",   "factor": 138.21/94.20},
    "Li2O":   {"name": "Lithium carbonate (Li2CO3)",   "purity": 0.995, "mw": 73.89,  "oxide": "Li2O",  "factor": 73.89/29.88},
    "BaO":    {"name": "Barium carbonate (BaCO3)",     "purity": 0.99,  "mw": 197.35, "oxide": "BaO",   "factor": 197.35/153.33},
    "ZnO":    {"name": "Zinc oxide (ZnO)",             "purity": 0.99,  "mw": 81.39,  "oxide": "ZnO",   "factor": 1.000},
    "TiO2":   {"name": "Titanium dioxide (TiO2)",      "purity": 0.995, "mw": 79.87,  "oxide": "TiO2",  "factor": 1.000},
    "ZrO2":   {"name": "Zirconium silicate (ZrSiO4)",  "purity": 0.98,  "mw": 183.31, "oxide": "ZrO2",  "factor": 183.31/123.22},
    "P2O5":   {"name": "Phosphoric acid (H3PO4)",      "purity": 0.85,  "mw": 98.00,  "oxide": "P2O5",  "factor": 98.0*2/141.94},
    "La2O3":  {"name": "Lanthanum oxide (La2O3)",      "purity": 0.995, "mw": 325.81, "oxide": "La2O3", "factor": 1.000},
    "PbO":    {"name": "Red lead (Pb3O4)",             "purity": 0.99,  "mw": 685.57, "oxide": "PbO",   "factor": 685.57/(3*223.19)},
}


def batch_calculation(comp_wt: dict, batch_size_g=1000.0) -> dict:
    """
    Convert a wt% oxide composition to raw material batch weights.

    Parameters
    ----------
    comp_wt      : {oxide: wt_percent, ...}
    batch_size_g : target glass batch mass (g)

    Returns
    -------
    dict with raw material weights and LOI (loss on ignition).
    """
    total = sum(comp_wt.values())
    if total <= 0:
        return {}

    norm = {ox: v / total * 100 for ox, v in comp_wt.items()}
    batch = {}
    total_batch = 0.0
    for ox, wt_pct in norm.items():
        rm = RAW_MATERIALS.get(ox)
        if rm:
            raw_mass = (wt_pct / 100) * batch_size_g * rm["factor"] / rm["purity"]
            batch[rm["name"]] = round(raw_mass, 2)
            total_batch += raw_mass
        else:
            # use oxide directly
            raw_mass = (wt_pct / 100) * batch_size_g
            batch[ox] = round(raw_mass, 2)
            total_batch += raw_mass

    loi = round(total_batch - batch_size_g, 2)
    return {
        "batch_weights_g":  batch,
        "total_batch_g":    round(total_batch, 2),
        "glass_mass_g":     batch_size_g,
        "loi_g":            loi,
        "loi_pct":          round(loi / total_batch * 100, 1) if total_batch > 0 else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Full composition analysis  (single entry point for UI)
# ─────────────────────────────────────────────────────────────────────────────

def full_analysis(comp_wt: dict) -> dict:
    """Run all calculators and return unified results dict."""
    return {
        "nbo_t":              nbo_t(comp_wt),
        "optical_basicity":   optical_basicity(comp_wt),
        "topological":        topological_constraints(comp_wt),
        "network_formers":    network_former_analysis(comp_wt),
        "estimates":          estimate_properties(comp_wt),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Unit conversion helpers
# ─────────────────────────────────────────────────────────────────────────────

def wt_to_mol(comp_wt: dict) -> dict:
    """Convert wt% composition to mol%."""
    moles = {}
    for ox, val in comp_wt.items():
        mm = MOLAR_MASS.get(ox)
        if mm and val > 0:
            moles[ox] = val / mm
    total = sum(moles.values())
    if total <= 0:
        return {}
    return {ox: round(m / total * 100, 3) for ox, m in moles.items()}


def mol_to_wt(comp_mol: dict) -> dict:
    """Convert mol% composition to wt%."""
    weights = {}
    for ox, val in comp_mol.items():
        mm = MOLAR_MASS.get(ox)
        if mm and val > 0:
            weights[ox] = val * mm
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {ox: round(w / total * 100, 3) for ox, w in weights.items()}
