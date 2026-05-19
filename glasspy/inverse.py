"""
Inverse design solver — find glass compositions that meet property targets.

Strategy (two-stage):
  1. Latin Hypercube Sampling (LHS) broad search across oxide ranges
  2. Genetic Algorithm (GA) refinement of best candidates

Both stages use the ML prediction models from glasspy.ml.

Output: ranked list of candidate compositions with predicted properties
        and estimated uncertainty.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
from typing import Optional
from config import OXIDES
import logging
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Score function
# ─────────────────────────────────────────────────────────────────────────────

def _score(predicted: dict, targets: list) -> float:
    """
    Sum of squared normalised residuals.
    targets = [{"prop": name, "target": v, "tolerance": t, "weight": w}, ...]
    Lower is better.  0 = perfect match.
    """
    total = 0.0
    for t in targets:
        pred_val = predicted.get(t["prop"])
        if pred_val is None:
            total += 1e6
            continue
        tol = t.get("tolerance", abs(t["target"]) * 0.1) or 1e-9
        w   = t.get("weight", 1.0)
        total += w * ((pred_val - t["target"]) / tol) ** 2
    return total


def _normalise_comp(comp: dict, active_oxides: list) -> dict:
    """Ensure active oxides sum to 100, clipping negatives."""
    # Clip
    comp = {ox: max(0.0, comp.get(ox, 0.0)) for ox in active_oxides}
    total = sum(comp.values())
    if total <= 0:
        # flat distribution
        v = 100.0 / len(active_oxides)
        return {ox: v for ox in active_oxides}
    return {ox: v / total * 100.0 for ox, v in comp.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Latin Hypercube Sampling
# ─────────────────────────────────────────────────────────────────────────────

def _lhs_sample(oxide_ranges: dict, n: int, rng) -> list:
    """
    Generate n compositions via LHS within oxide_ranges.
    oxide_ranges = {oxide: (lo, hi), ...}
    Returns list of {oxide: value} dicts (unnormalised, then normalised to 100).
    """
    oxides = list(oxide_ranges.keys())
    d = len(oxides)
    # LHS: each dimension divided into n equal intervals, one sample per interval
    result = []
    for i in range(n):
        comp = {}
        for ox in oxides:
            lo, hi = oxide_ranges[ox]
            # stratified uniform
            u = (rng.random() + i) / n
            comp[ox] = lo + u * (hi - lo)
        result.append(comp)
    rng.shuffle(result)
    # Normalise each composition
    return [_normalise_comp(c, oxides) for c in result]


# ─────────────────────────────────────────────────────────────────────────────
# Genetic Algorithm helpers
# ─────────────────────────────────────────────────────────────────────────────

def _crossover(p1: dict, p2: dict, oxides: list, rng) -> dict:
    """Single-point crossover on sorted oxide list."""
    k = rng.integers(1, len(oxides))
    child = {}
    for i, ox in enumerate(oxides):
        child[ox] = p1[ox] if i < k else p2[ox]
    return _normalise_comp(child, oxides)


def _mutate(comp: dict, oxide_ranges: dict, oxides: list, rng, sigma=0.05) -> dict:
    """Gaussian mutation with range clipping."""
    new = dict(comp)
    n_mut = max(1, rng.integers(1, max(2, len(oxides) // 4)))
    idx   = rng.choice(len(oxides), size=n_mut, replace=False)
    for i in idx:
        ox  = oxides[i]
        lo, hi = oxide_ranges[ox]
        step = sigma * (hi - lo)
        new[ox] = np.clip(comp[ox] + rng.normal(0, step), lo, hi)
    return _normalise_comp(new, oxides)


# ─────────────────────────────────────────────────────────────────────────────
# Main solver
# ─────────────────────────────────────────────────────────────────────────────

def inverse_design(
    oxide_ranges:  dict,
    targets:       list,
    prop_names:    Optional[list] = None,
    comp_type:     str  = "mol_pct",
    model_type:    str  = "random_forest",
    n_lhs:         int  = 2000,
    n_top_lhs:     int  = 200,
    ga_generations: int = 80,
    ga_pop:        int  = 100,
    random_seed:   int  = 42,
    top_n:         int  = 20,
) -> list:
    """
    Find glass compositions that meet property targets.

    Parameters
    ----------
    oxide_ranges : {oxide: (lo, hi)} — composition search space (mol% or wt%)
    targets      : [{"prop": name, "target": value, "tolerance": ±tol, "weight": w}, ...]
    prop_names   : list of properties to predict (defaults to targets props)
    comp_type    : "mol_pct" | "wt_pct"
    model_type   : ML model type (see glasspy.ml)
    n_lhs        : number of LHS candidates
    n_top_lhs    : top N from LHS passed to GA
    ga_generations: GA iteration count
    ga_pop       : GA population size
    random_seed  : reproducibility
    top_n        : solutions to return

    Returns
    -------
    List of dicts, each containing:
      composition, predicted_properties, score, rank
    """
    from glasspy.ml import predict_batch, train_model

    if prop_names is None:
        prop_names = [t["prop"] for t in targets]

    # Ensure models are trained
    for prop in prop_names:
        try:
            train_model(prop, comp_type=comp_type, model_type=model_type)
        except Exception as e:
            logger.warning(f"Could not train model for {prop}: {e}")

    oxides = list(oxide_ranges.keys())
    rng    = np.random.default_rng(random_seed)

    # ── Stage 1: LHS broad search ────────────────────────────────────────────
    logger.info(f"Inverse design: LHS sampling {n_lhs} candidates…")
    lhs_comps = _lhs_sample(oxide_ranges, n_lhs, rng)
    lhs_preds = predict_batch(lhs_comps, prop_names, comp_type=comp_type,
                              model_type=model_type)
    lhs_scored = [(c, p, _score(p, targets))
                  for c, p in zip(lhs_comps, lhs_preds)]
    lhs_scored.sort(key=lambda x: x[2])
    # seed GA with top N from LHS
    seed_pop = [c for c, p, s in lhs_scored[:n_top_lhs]]

    # ── Stage 2: Genetic Algorithm ───────────────────────────────────────────
    logger.info(f"GA refinement: {ga_generations} gen × {ga_pop} pop…")
    population = seed_pop[:ga_pop]
    # Fill rest randomly if needed
    while len(population) < ga_pop:
        population.append(lhs_comps[rng.integers(len(lhs_comps))])

    best_score = float("inf")
    for gen in range(ga_generations):
        preds  = predict_batch(population, prop_names, comp_type=comp_type,
                               model_type=model_type)
        scored = sorted(zip(population, preds),
                        key=lambda x: _score(x[1], targets))
        # Elitism: keep top 20%
        elite_n    = max(2, ga_pop // 5)
        elite      = [c for c, _ in scored[:elite_n]]
        new_pop    = list(elite)

        # Crossover + mutation
        while len(new_pop) < ga_pop:
            i1, i2 = rng.choice(elite_n, size=2, replace=False)
            child  = _crossover(elite[i1], elite[i2], oxides, rng)
            child  = _mutate(child, oxide_ranges, oxides, rng)
            new_pop.append(child)

        population = new_pop
        current_best = _score(scored[0][1], targets)
        if current_best < best_score:
            best_score = current_best
            if gen % 20 == 0:
                logger.info(f"  Gen {gen:3d}: best score = {best_score:.4f}")

    # ── Final ranking ─────────────────────────────────────────────────────────
    all_comps = list({
        tuple(sorted(c.items())): c
        for c in (lhs_comps + population)
    }.values())
    final_preds = predict_batch(all_comps[:5000], prop_names,
                                comp_type=comp_type, model_type=model_type)
    final_scored = sorted(zip(all_comps[:5000], final_preds),
                          key=lambda x: _score(x[1], targets))

    results = []
    for rank, (comp, pred) in enumerate(final_scored[:top_n], start=1):
        score = _score(pred, targets)
        # Extract just the value keys (not _lower/_upper)
        props = {k: v for k, v in pred.items()
                 if not k.endswith(("_lower", "_upper")) and k in prop_names}
        intervals = {k.replace("_lower", ""): {"lower": pred.get(k), "upper": pred.get(k.replace("_lower","_upper"))}
                     for k in pred if k.endswith("_lower")}
        results.append({
            "rank":                rank,
            "composition":         {ox: round(v, 2) for ox, v in comp.items() if v > 0.05},
            "predicted_properties": {p: round(float(v), 4) if v else None for p, v in props.items()},
            "uncertainty":         intervals,
            "score":               round(score, 5),
        })

    logger.info(f"Inverse design complete. Best score: {results[0]['score']:.4f}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Pareto front (multi-objective)
# ─────────────────────────────────────────────────────────────────────────────

def pareto_front(results: list, obj1: str, obj2: str) -> list:
    """
    Return the Pareto-optimal subset from results for two objectives
    (both minimised by default — pass negated values for maximisation).
    """
    dominated = set()
    for i, ri in enumerate(results):
        pi = ri["predicted_properties"]
        vi1, vi2 = pi.get(obj1, 1e9), pi.get(obj2, 1e9)
        for j, rj in enumerate(results):
            if i == j:
                continue
            pj = rj["predicted_properties"]
            vj1, vj2 = pj.get(obj1, 1e9), pj.get(obj2, 1e9)
            if vj1 <= vi1 and vj2 <= vi2 and (vj1 < vi1 or vj2 < vi2):
                dominated.add(i)
                break
    return [r for i, r in enumerate(results) if i not in dominated]
