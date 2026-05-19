"""
Machine-learning property prediction for glass compositions.

Supports:
  - RandomForestRegressor  (default — best for tabular glass data)
  - GradientBoostingRegressor
  - ExtraTreesRegressor
  - External model loading from joblib/pickle file or GitHub URL

Features:
  - Lazy-train on first request, then persist to MODEL_DIR
  - Uncertainty quantification via prediction intervals (RF individual trees)
  - Feature importance reporting
  - Batch prediction from pandas DataFrame
"""
import os, sys, json, hashlib, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
import joblib
from pathlib import Path
from config import OXIDES, MODEL_DIR

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Model registry
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_MODELS = {
    "random_forest": {
        "cls":    "sklearn.ensemble.RandomForestRegressor",
        "kwargs": {"n_estimators": 200, "max_features": "sqrt",
                   "min_samples_leaf": 2, "n_jobs": -1, "random_state": 42},
        "label":  "Random Forest",
    },
    "gradient_boosting": {
        "cls":    "sklearn.ensemble.GradientBoostingRegressor",
        "kwargs": {"n_estimators": 300, "learning_rate": 0.05,
                   "max_depth": 4, "subsample": 0.8, "random_state": 42},
        "label":  "Gradient Boosting",
    },
    "extra_trees": {
        "cls":    "sklearn.ensemble.ExtraTreesRegressor",
        "kwargs": {"n_estimators": 200, "min_samples_leaf": 2,
                   "n_jobs": -1, "random_state": 42},
        "label":  "Extra Trees",
    },
}


def _import_class(dotted_path):
    parts = dotted_path.rsplit(".", 1)
    module = __import__(parts[0], fromlist=[parts[1]])
    return getattr(module, parts[1])


# ─────────────────────────────────────────────────────────────────────────────
# Model cache key
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(prop_name, comp_type, model_type):
    raw = f"{prop_name}__{comp_type}__{model_type}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _model_path(prop_name, comp_type, model_type):
    key = _cache_key(prop_name, comp_type, model_type)
    return Path(MODEL_DIR) / f"model_{key}.joblib"


def _meta_path(prop_name, comp_type, model_type):
    key = _cache_key(prop_name, comp_type, model_type)
    return Path(MODEL_DIR) / f"meta_{key}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def train_model(prop_name, comp_type="mol_pct", model_type="random_forest",
                force_retrain=False):
    """
    Train a model for the given property.  Results are cached to disk.

    Returns
    -------
    dict with keys: model_type, prop_name, n_train, cv_r2, cv_rmse,
                    feature_importance (top 15 oxides),
                    trained_at, model_path
    """
    from glasspy.db import get_training_data
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    os.makedirs(MODEL_DIR, exist_ok=True)
    mp = _model_path(prop_name, comp_type, model_type)
    mm = _meta_path(prop_name, comp_type, model_type)

    if mp.exists() and mm.exists() and not force_retrain:
        with open(mm) as f:
            return json.load(f)

    logger.info(f"Training {model_type} for {prop_name} ({comp_type})…")
    X, y = get_training_data(prop_name, comp_type=comp_type)
    if X is None or len(X) < 30:
        raise ValueError(f"Not enough data to train: {prop_name} ({comp_type}). "
                         f"Need ≥30 samples, got {len(X) if X is not None else 0}.")

    reg_info = SUPPORTED_MODELS.get(model_type)
    if reg_info is None:
        raise ValueError(f"Unknown model type: {model_type!r}")
    cls = _import_class(reg_info["cls"])
    reg = cls(**reg_info["kwargs"])

    # 5-fold cross-validation
    scores_r2   = cross_val_score(reg, X, y, cv=5, scoring="r2", n_jobs=-1)
    scores_rmse = cross_val_score(reg, X, y, cv=5,
                                  scoring="neg_root_mean_squared_error", n_jobs=-1)

    # Fit on full data
    reg.fit(X, y)
    joblib.dump(reg, mp)

    # Feature importances (RF/ET only)
    importance = {}
    if hasattr(reg, "feature_importances_"):
        imp = reg.feature_importances_
        top_idx = np.argsort(imp)[::-1][:15]
        importance = {X.columns[i]: round(float(imp[i]), 4) for i in top_idx}

    from datetime import datetime
    meta = {
        "model_type":          model_type,
        "prop_name":           prop_name,
        "comp_type":           comp_type,
        "n_train":             int(len(X)),
        "cv_r2":               round(float(scores_r2.mean()), 4),
        "cv_r2_std":           round(float(scores_r2.std()), 4),
        "cv_rmse":             round(float(-scores_rmse.mean()), 4),
        "feature_importance":  importance,
        "trained_at":          datetime.now().isoformat(timespec="seconds"),
        "model_path":          str(mp),
        "n_features":          int(X.shape[1]),
    }
    with open(mm, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(f"  Done. R²={meta['cv_r2']:.3f}  RMSE={meta['cv_rmse']:.3f}  n={meta['n_train']:,}")
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Prediction
# ─────────────────────────────────────────────────────────────────────────────

def predict(comp_dict, prop_name, comp_type="mol_pct", model_type="random_forest",
            return_interval=True):
    """
    Predict a property value for a single composition.

    Parameters
    ----------
    comp_dict : {oxide: value, ...}  — composition in mol% or wt%
    prop_name : target property name
    comp_type : "mol_pct" | "wt_pct"
    model_type: model key from SUPPORTED_MODELS

    Returns
    -------
    dict: value, lower_90, upper_90 (if RF/ET), model_type, prop_name
    """
    import pandas as pd

    mp = _model_path(prop_name, comp_type, model_type)
    if not mp.exists():
        # auto-train
        train_model(prop_name, comp_type=comp_type, model_type=model_type)

    reg = joblib.load(mp)

    # Build feature vector aligned to OXIDES order
    X = pd.DataFrame([{ox: comp_dict.get(ox, 0.0) for ox in OXIDES}])

    pred = float(reg.predict(X)[0])

    result = {
        "value":      round(pred, 4),
        "model_type": model_type,
        "prop_name":  prop_name,
        "comp_type":  comp_type,
    }

    # Prediction interval from individual trees (RF / ET)
    if return_interval and hasattr(reg, "estimators_"):
        tree_preds = np.array([t.predict(X)[0] for t in reg.estimators_])
        p5, p95 = np.percentile(tree_preds, [5, 95])
        result["lower_90"] = round(float(p5), 4)
        result["upper_90"] = round(float(p95), 4)
        result["std"]      = round(float(tree_preds.std()), 4)

    return result


def predict_batch(compositions, prop_names, comp_type="mol_pct",
                  model_type="random_forest"):
    """
    Predict multiple properties for multiple compositions.

    Parameters
    ----------
    compositions : list of {oxide: value} dicts
    prop_names   : list of property names
    comp_type    : composition type
    model_type   : model type

    Returns
    -------
    list of dicts [{oxide...} + {prop: value, prop_lower, prop_upper}]
    """
    import pandas as pd
    results = []
    for comp in compositions:
        row = dict(comp)
        for prop in prop_names:
            try:
                r = predict(comp, prop, comp_type=comp_type,
                            model_type=model_type, return_interval=True)
                row[prop] = r["value"]
                row[f"{prop}_lower"] = r.get("lower_90")
                row[f"{prop}_upper"] = r.get("upper_90")
            except Exception as e:
                row[prop] = None
                logger.warning(f"Prediction failed for {prop}: {e}")
        results.append(row)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# External model loading
# ─────────────────────────────────────────────────────────────────────────────

def load_external_model(source, prop_name, model_name="external"):
    """
    Load a model from a local .joblib/.pkl path or a GitHub raw URL.
    The model must accept a pandas DataFrame of OXIDE features.

    Parameters
    ----------
    source     : local file path or https://raw.githubusercontent.com/...
    prop_name  : property this model predicts
    model_name : identifier (used in meta)

    Returns
    -------
    path to cached model file
    """
    os.makedirs(MODEL_DIR, exist_ok=True)
    dest = Path(MODEL_DIR) / f"ext_{model_name}_{prop_name}.joblib"

    if source.startswith("http"):
        import urllib.request
        logger.info(f"Downloading model from {source}")
        urllib.request.urlretrieve(source, dest)
    else:
        import shutil
        shutil.copy2(source, dest)

    # Quick sanity check
    reg = joblib.load(dest)
    if not hasattr(reg, "predict"):
        raise ValueError("Loaded object has no .predict() method — not a valid sklearn model.")

    logger.info(f"External model loaded: {dest}")
    return str(dest)


# ─────────────────────────────────────────────────────────────────────────────
# Model inventory
# ─────────────────────────────────────────────────────────────────────────────

def list_trained_models():
    """Return list of all cached model metadata."""
    models = []
    p = Path(MODEL_DIR)
    if not p.exists():
        return models
    for mf in sorted(p.glob("meta_*.json")):
        with open(mf) as f:
            models.append(json.load(f))
    return models


def delete_model(prop_name, comp_type, model_type):
    """Delete cached model and metadata."""
    mp = _model_path(prop_name, comp_type, model_type)
    mm = _meta_path(prop_name, comp_type, model_type)
    for p in (mp, mm):
        if p.exists():
            p.unlink()
