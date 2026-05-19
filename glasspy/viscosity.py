"""
Viscosity models for glass melts.

Implemented models:
  - MYEGA  (Mauro-Yue-Ellison-Gupta-Allan, 2009)
  - VFT    (Vogel-Fulcher-Tammann)
  - AM     (Avramov-Milchev, 1995)

All models work with log10(viscosity / Pa·s).
"""
import numpy as np
from scipy.optimize import curve_fit, minimize
from dataclasses import dataclass, field
from typing import Optional

# ── Reference viscosity points (log10 Pa·s) ──────────────────────────────────
VISC_POINTS = {
    "liquidus":    1.0,   # approximate onset of crystallisation
    "working":     4.0,   # hot-working / gob delivery
    "softening":   6.6,   # Littleton softening point (dilatometric)
    "annealing":  12.0,   # annealing point (viscous relaxation ~15 min)
    "strain":     13.5,   # strain point (relaxation essentially stopped)
}


# ─────────────────────────────────────────────────────────────────────────────
# Model functions  (T in Kelvin)
# ─────────────────────────────────────────────────────────────────────────────

def myega(T, log_eta_inf, Tg, m):
    """
    MYEGA viscosity model (Mauro et al., JACS 2009).

    log10 η(T) = log_eta_inf
                 + (12 - log_eta_inf) * (Tg/T)
                 * exp[(m/(12 - log_eta_inf) - 1) * (Tg/T - 1)]

    Parameters
    ----------
    T           : temperature (K)
    log_eta_inf : log10 viscosity at infinite temperature
    Tg          : glass transition temperature (K) — isokom at log η = 12
    m           : fragility index (dimensionless, typically 20–100)
    """
    T = np.asarray(T, dtype=float)
    ratio = Tg / T
    exponent = (m / (12.0 - log_eta_inf) - 1.0) * (ratio - 1.0)
    return log_eta_inf + (12.0 - log_eta_inf) * ratio * np.exp(exponent)


def vft(T, A, B, T0):
    """
    VFT model: log10 η(T) = A + B / (T - T0)

    Parameters
    ----------
    A  : log10 viscosity at infinite T (dimensionless, typically –2 to –4)
    B  : pseudo-activation energy constant (K)
    T0 : Vogel temperature (K) — divergence temperature
    """
    T = np.asarray(T, dtype=float)
    return A + B / (T - T0)


def am(T, log_eta_inf, T_ref, alpha):
    """
    Avramov-Milchev model: log10 η(T) = log_eta_inf + (T_ref/T)^alpha

    Parameters
    ----------
    log_eta_inf : log10 viscosity at infinite temperature
    T_ref       : reference temperature (related to activation energy)
    alpha       : structural disorder parameter
    """
    T = np.asarray(T, dtype=float)
    return log_eta_inf + (T_ref / T) ** alpha


# ─────────────────────────────────────────────────────────────────────────────
# Fit result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ViscFitResult:
    model:      str
    params:     dict
    param_err:  dict
    r2:         float
    rmse:       float
    T_data:     list
    logv_data:  list
    # Derived characteristic temperatures (°C)
    T_liquidus:   Optional[float] = None
    T_working:    Optional[float] = None
    T_softening:  Optional[float] = None
    T_annealing:  Optional[float] = None
    T_strain:     Optional[float] = None
    Tg_C:         Optional[float] = None
    fragility:    Optional[float] = None

    def to_dict(self):
        return {
            "model":      self.model,
            "params":     self.params,
            "param_err":  self.param_err,
            "r2":         round(self.r2, 5),
            "rmse":       round(self.rmse, 4),
            "T_data":     self.T_data,
            "logv_data":  self.logv_data,
            "T_liquidus":  _fmt(self.T_liquidus),
            "T_working":   _fmt(self.T_working),
            "T_softening": _fmt(self.T_softening),
            "T_annealing": _fmt(self.T_annealing),
            "T_strain":    _fmt(self.T_strain),
            "Tg_C":        _fmt(self.Tg_C),
            "fragility":   _fmt(self.fragility),
        }


def _fmt(v):
    return round(v, 1) if v is not None and np.isfinite(v) else None


# ─────────────────────────────────────────────────────────────────────────────
# Inverse T-solver: given a target log η, find T
# ─────────────────────────────────────────────────────────────────────────────

def _solve_T(model_fn, params_tuple, log_target, T_lo=300.0, T_hi=3000.0):
    """Binary-search T such that model_fn(T, *params) ≈ log_target."""
    try:
        from scipy.optimize import brentq
        f = lambda T: model_fn(T, *params_tuple) - log_target
        # check bracket
        if f(T_lo) * f(T_hi) > 0:
            return None
        return brentq(f, T_lo, T_hi, xtol=0.1)
    except Exception:
        return None


def _characteristic_temps(model_fn, params_tuple):
    temps = {}
    for name, logv in VISC_POINTS.items():
        T_K = _solve_T(model_fn, params_tuple, logv)
        temps[name] = T_K - 273.15 if T_K is not None else None
    return temps


def _r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Public fit function
# ─────────────────────────────────────────────────────────────────────────────

def fit_viscosity(temperatures, log_viscosities, model="myega"):
    """
    Fit a viscosity model to temperature–viscosity data.

    Parameters
    ----------
    temperatures    : array-like, T in °C  (will be converted to K internally)
    log_viscosities : array-like, log10(η / Pa·s)
    model           : "myega" | "vft" | "am"

    Returns
    -------
    ViscFitResult or raises ValueError on failure.
    """
    T = np.asarray(temperatures, dtype=float) + 273.15  # °C → K
    lv = np.asarray(log_viscosities, dtype=float)

    if len(T) < 3:
        raise ValueError("At least 3 data points are required for fitting.")

    if model == "myega":
        fn = myega
        # Initial guesses: log_eta_inf=-3, Tg ~ midpoint T, m=40
        Tg0 = float(np.median(T))
        p0  = [-3.0, Tg0, 40.0]
        bounds = ([-10, 300, 10], [2, 2500, 200])
        pnames = ["log_eta_inf", "Tg_K", "m"]

    elif model == "vft":
        fn = vft
        # A~-3, B~5000, T0 ~ Tmin - 200
        p0  = [-3.0, 5000.0, max(200.0, T.min() - 200)]
        bounds = ([-10, 100, 50], [2, 100000, T.min() - 10])
        pnames = ["A", "B", "T0_K"]

    elif model == "am":
        fn = am
        p0  = [-3.0, float(np.mean(T)), 5.0]
        bounds = ([-10, 100, 0.5], [2, 5000, 30])
        pnames = ["log_eta_inf", "T_ref_K", "alpha"]

    else:
        raise ValueError(f"Unknown model: {model!r}. Choose myega, vft, or am.")

    try:
        popt, pcov = curve_fit(fn, T, lv, p0=p0, bounds=bounds,
                               maxfev=20000, method="trf")
    except Exception as e:
        raise ValueError(f"Fit did not converge: {e}")

    perr = np.sqrt(np.diag(pcov)) if pcov is not None else np.zeros(len(popt))
    lv_pred = fn(T, *popt)
    r2   = _r2(lv, lv_pred)
    rmse = float(np.sqrt(np.mean((lv - lv_pred) ** 2)))

    params    = {k: float(round(v, 4)) for k, v in zip(pnames, popt)}
    param_err = {k: float(round(v, 4)) for k, v in zip(pnames, perr)}

    ctmps = _characteristic_temps(fn, tuple(popt))

    result = ViscFitResult(
        model      = model,
        params     = params,
        param_err  = param_err,
        r2         = float(r2),
        rmse       = rmse,
        T_data     = list(map(float, temperatures)),
        logv_data  = list(map(float, log_viscosities)),
        T_liquidus  = ctmps.get("liquidus"),
        T_working   = ctmps.get("working"),
        T_softening = ctmps.get("softening"),
        T_annealing = ctmps.get("annealing"),
        T_strain    = ctmps.get("strain"),
    )

    # Model-specific extras
    if model == "myega":
        result.Tg_C     = float(popt[1] - 273.15)
        result.fragility = float(popt[2])
    elif model == "vft":
        # Derive Tg and fragility from VFT: log12 isokom
        Tg_K = _solve_T(vft, tuple(popt), 12.0)
        if Tg_K:
            result.Tg_C = Tg_K - 273.15
            # fragility = d(log η)/d(Tg/T) at T=Tg
            A, B, T0 = popt
            result.fragility = float(B * Tg_K / (Tg_K - T0) ** 2 / np.log(10))
    elif model == "am":
        Tg_K = _solve_T(am, tuple(popt), 12.0)
        if Tg_K:
            result.Tg_C = Tg_K - 273.15

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Predict curve for plotting
# ─────────────────────────────────────────────────────────────────────────────

def predict_curve(fit_result: ViscFitResult, T_min_C=200, T_max_C=1800, n=300):
    """Return (T_list_C, logv_list) dense curve for plotting."""
    T_C  = np.linspace(T_min_C, T_max_C, n)
    T_K  = T_C + 273.15
    fn_map = {"myega": myega, "vft": vft, "am": am}
    fn   = fn_map[fit_result.model]
    popt = list(fit_result.params.values())
    logv = fn(T_K, *popt)
    return T_C.tolist(), logv.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Working range calculator
# ─────────────────────────────────────────────────────────────────────────────

def working_range(fit_result: ViscFitResult):
    """
    Return the working range ΔT = T_working − T_softening (°C).
    Wider = easier to work (soda-lime ~180°C, borosilicate ~100°C).
    """
    if fit_result.T_working is None or fit_result.T_softening is None:
        return None
    return round(fit_result.T_working - fit_result.T_softening, 1)
