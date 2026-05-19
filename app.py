"""
Zach V1 — Glass Informatics Platform
Flask application — all routes and API endpoints.
"""
import os, sys, json, threading, logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DB_PATH, USER_DB, MODEL_DIR, PORT, DEBUG, SECRET_KEY, OXIDES  # noqa: F401
import glasspy.db as db
from glasspy.properties import full_analysis, batch_calculation, wt_to_mol, mol_to_wt
from glasspy.viscosity import fit_viscosity, predict_curve, working_range

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("zachv1")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY
CORS(app)

# Initialise user database
db.init_user_db()

# ── Background model pre-training ────────────────────────────────────────────
# These are the 5 most data-rich properties; train on first launch.
PRELOAD_PROPS = [
    ("density",                  "mol_pct"),
    ("tg_celsius",               "mol_pct"),
    ("thermal_expansion_coeff",  "mol_pct"),
    ("refractive_index_nD",      "mol_pct"),
    ("liquidus_temp",            "mol_pct"),
]
_preload_status = {}   # prop → "pending" | "training" | "done" | "error:<msg>"


def _preload_worker():
    from glasspy.ml import train_model, _model_path, _meta_path
    for prop, ctype in PRELOAD_PROPS:
        mp = _model_path(prop, ctype, "random_forest")
        if mp.exists():
            _preload_status[prop] = "done"
            continue
        _preload_status[prop] = "training"
        try:
            train_model(prop, comp_type=ctype, model_type="random_forest")
            _preload_status[prop] = "done"
            logger.info(f"Pre-trained model: {prop}")
        except Exception as e:
            _preload_status[prop] = f"error:{e}"
            logger.warning(f"Could not pre-train {prop}: {e}")


def _start_preload():
    for prop, _ in PRELOAD_PROPS:
        _preload_status[prop] = "pending"
    t = threading.Thread(target=_preload_worker, daemon=True)
    t.start()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ok(data=None, **kwargs):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(kwargs)
    return jsonify(payload)


def _err(msg, code=400):
    return jsonify({"ok": False, "error": str(msg)}), code


def _parse_body():
    if request.is_json:
        return request.get_json(force=True) or {}
    try:
        return json.loads(request.data) if request.data else {}
    except Exception:
        return request.form.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    stats = db.get_stats()
    return render_template("dashboard.html", stats=stats, oxides=OXIDES)


@app.route("/explore")
def explore():
    return render_template("explore.html", oxides=OXIDES)


@app.route("/glass/<int:glass_id>")
def glass_detail(glass_id):
    source = request.args.get("source", "sciglass")
    glass  = db.get_glass(glass_id, source=source)
    if not glass:
        return render_template("404.html"), 404
    return render_template("glass_detail.html", glass=glass, oxides=OXIDES)


@app.route("/add-glass")
def add_glass_page():
    return render_template("add_glass.html", oxides=OXIDES)


@app.route("/viscosity")
def viscosity_page():
    return render_template("viscosity.html", oxides=OXIDES)


@app.route("/predict")
def predict_page():
    return render_template("predict.html", oxides=OXIDES,
                           preload_props=PRELOAD_PROPS)


@app.route("/inverse")
def inverse_page():
    return render_template("inverse.html", oxides=OXIDES)


@app.route("/tools")
def tools_page():
    return render_template("tools.html", oxides=OXIDES)


@app.route("/ternary")
def ternary_page():
    return render_template("ternary.html", oxides=OXIDES)


@app.route("/visualize")
def visualize_page():
    return render_template("visualize.html", oxides=OXIDES)


@app.route("/similar")
def similar_page():
    return render_template("similar.html", oxides=OXIDES)


@app.route("/contact")
def contact_page():
    return render_template("contact.html", oxides=OXIDES)


@app.route("/about")
def about_page():
    return render_template("about.html", oxides=OXIDES)


# ─────────────────────────────────────────────────────────────────────────────
# API — Search
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/search", methods=["POST"])
def api_search():
    try:
        body = _parse_body()
        rows, total = db.search_glasses(
            oxide_filters  = body.get("oxide_filters"),
            prop_filters   = body.get("prop_filters"),
            comp_type      = body.get("comp_type"),
            limit          = min(int(body.get("limit", 100)), 500),
            offset         = int(body.get("offset", 0)),
            sort_by        = body.get("sort_by", "id"),
            include_details= bool(body.get("include_details", True)),
        )
        return _ok({"rows": rows, "total": total})
    except Exception as e:
        logger.exception("search failed")
        return _err(str(e))


@app.route("/api/glass/<int:glass_id>")
def api_glass(glass_id):
    source = request.args.get("source", "sciglass")
    glass  = db.get_glass(glass_id, source=source)
    if not glass:
        return _err("Glass not found", 404)
    return _ok(glass)


@app.route("/api/stats")
def api_stats():
    return _ok(db.get_stats())


@app.route("/api/property-stats/<prop_name>")
def api_prop_stats(prop_name):
    r = db.get_property_stats(prop_name)
    if not r:
        return _err(f"No data for {prop_name}", 404)
    return _ok(r)


@app.route("/api/ternary", methods=["POST"])
def api_ternary():
    try:
        body = _parse_body()
        data = db.get_ternary_data(
            body["ox1"], body["ox2"], body["ox3"],
            body["prop_name"],
            comp_type=body.get("comp_type", "mol_pct"),
        )
        return _ok(data)
    except Exception as e:
        return _err(str(e))


@app.route("/api/user-glasses")
def api_user_glasses():
    return _ok(db.list_user_glasses())


# ─────────────────────────────────────────────────────────────────────────────
# API — Add glass
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/add-glass", methods=["POST"])
def api_add_glass():
    try:
        body = _parse_body()
        if not body.get("compositions"):
            return _err("compositions array is required")
        gid = db.save_user_glass(
            body.get("name", "Unnamed glass"),
            body.get("source", "experimental"),
            body.get("notes", ""),
            body["compositions"],
            body.get("properties", []),
            body.get("visc_points", []),
        )
        return _ok({"id": gid, "name": body.get("name")})
    except Exception as e:
        logger.exception("add-glass failed")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Viscosity
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/viscosity/fit", methods=["POST"])
def api_visc_fit():
    try:
        body  = _parse_body()
        temps = body.get("temperatures")
        logvs = body.get("log_viscosities")
        if not temps or not logvs:
            return _err("temperatures and log_viscosities required")
        result = fit_viscosity(temps, logvs, model=body.get("model", "myega"))
        curve  = predict_curve(result)
        out    = result.to_dict()
        out["curve_T"]         = curve[0]
        out["curve_logv"]      = curve[1]
        out["working_range_C"] = working_range(result)
        return _ok(out)
    except Exception as e:
        logger.exception("viscosity fit failed")
        return _err(str(e))


@app.route("/api/viscosity/compare", methods=["POST"])
def api_visc_compare():
    try:
        body  = _parse_body()
        temps = body.get("temperatures")
        logvs = body.get("log_viscosities")
        if not temps or not logvs:
            return _err("temperatures and log_viscosities required")
        out = {}
        for model in ("myega", "vft", "am"):
            try:
                r  = fit_viscosity(temps, logvs, model=model)
                cv = predict_curve(r)
                d  = r.to_dict()
                d["curve_T"]         = cv[0]
                d["curve_logv"]      = cv[1]
                d["working_range_C"] = working_range(r)
                out[model] = d
            except Exception as me:
                out[model] = {"error": str(me)}
        return _ok(out)
    except Exception as e:
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Property tools
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/tools/analyse", methods=["POST"])
def api_tools_analyse():
    try:
        body    = _parse_body()
        comp_wt = {k: float(v) for k, v in body.get("composition", {}).items()
                   if float(v) > 0}
        if not comp_wt:
            return _err("composition required")
        return _ok(full_analysis(comp_wt))
    except Exception as e:
        logger.exception("analyse failed")
        return _err(str(e))


@app.route("/api/tools/batch", methods=["POST"])
def api_tools_batch():
    try:
        body       = _parse_body()
        comp_wt    = {k: float(v) for k, v in body.get("composition", {}).items()
                      if float(v) > 0}
        batch_size = float(body.get("batch_size_g", 1000))
        return _ok(batch_calculation(comp_wt, batch_size_g=batch_size))
    except Exception as e:
        return _err(str(e))


@app.route("/api/tools/convert", methods=["POST"])
def api_tools_convert():
    try:
        body      = _parse_body()
        comp      = {k: float(v) for k, v in body.get("composition", {}).items()
                     if float(v) > 0}
        direction = body.get("direction", "wt_to_mol")
        result    = wt_to_mol(comp) if direction == "wt_to_mol" else mol_to_wt(comp)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — ML prediction
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/predict", methods=["POST"])
def api_predict():
    try:
        from glasspy.ml import predict
        body      = _parse_body()
        comp      = {k: float(v) for k, v in body.get("composition", {}).items()
                     if float(v) > 0}
        prop_name = body.get("prop_name")
        if not prop_name:
            return _err("prop_name required")
        result = predict(comp, prop_name,
                         comp_type  = body.get("comp_type", "mol_pct"),
                         model_type = body.get("model_type", "random_forest"))
        return _ok(result)
    except Exception as e:
        logger.exception("predict failed")
        return _err(str(e))


@app.route("/api/predict/batch", methods=["POST"])
def api_predict_batch():
    try:
        from glasspy.ml import predict_batch
        body       = _parse_body()
        comps      = body.get("compositions", [])
        prop_names = body.get("prop_names", [])
        if not comps or not prop_names:
            return _err("compositions and prop_names required")
        results = predict_batch(comps, prop_names,
                                comp_type  = body.get("comp_type", "mol_pct"),
                                model_type = body.get("model_type", "random_forest"))
        return _ok(results)
    except Exception as e:
        logger.exception("predict_batch failed")
        return _err(str(e))


@app.route("/api/ml/models")
def api_ml_models():
    try:
        from glasspy.ml import list_trained_models
        models = list_trained_models()
        return _ok({"models": models, "preload_status": _preload_status})
    except Exception as e:
        return _err(str(e))


@app.route("/api/ml/preload-status")
def api_preload_status():
    return _ok(_preload_status)


@app.route("/api/ml/train", methods=["POST"])
def api_ml_train():
    try:
        from glasspy.ml import train_model
        body      = _parse_body()
        prop_name = body.get("prop_name")
        if not prop_name:
            return _err("prop_name required")
        meta = train_model(prop_name,
                           comp_type  = body.get("comp_type", "mol_pct"),
                           model_type = body.get("model_type", "random_forest"),
                           force_retrain = bool(body.get("force_retrain", False)))
        return _ok(meta)
    except Exception as e:
        logger.exception("train failed")
        return _err(str(e))


@app.route("/api/ml/load-external", methods=["POST"])
def api_ml_load_external():
    try:
        from glasspy.ml import load_external_model
        body      = _parse_body()
        source    = body.get("source")
        prop_name = body.get("prop_name")
        if not source or not prop_name:
            return _err("source and prop_name required")
        path = load_external_model(source, prop_name,
                                   model_name=body.get("model_name", "external"))
        return _ok({"path": path})
    except Exception as e:
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Inverse design
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/inverse", methods=["POST"])
def api_inverse():
    try:
        from glasspy.inverse import inverse_design
        body         = _parse_body()
        oxide_ranges = body.get("oxide_ranges", {})
        targets      = body.get("targets", [])
        if not oxide_ranges:
            return _err("oxide_ranges required")
        if not targets:
            return _err("targets required")
        results = inverse_design(
            oxide_ranges    = {ox: tuple(r) for ox, r in oxide_ranges.items()},
            targets         = targets,
            comp_type       = body.get("comp_type", "mol_pct"),
            model_type      = body.get("model_type", "random_forest"),
            n_lhs           = int(body.get("n_lhs", 2000)),
            ga_generations  = int(body.get("ga_generations", 80)),
            ga_pop          = int(body.get("ga_pop", 100)),
            top_n           = int(body.get("top_n", 20)),
        )
        return _ok(results)
    except Exception as e:
        logger.exception("inverse design failed")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Export
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/export/search", methods=["POST"])
def api_export_search():
    try:
        import io, csv
        body = _parse_body()
        rows, _ = db.search_glasses(
            oxide_filters   = body.get("oxide_filters"),
            prop_filters    = body.get("prop_filters"),
            comp_type       = body.get("comp_type"),
            limit           = 5000,
            offset          = 0,
            include_details = True,
        )
        if not rows:
            return _err("No results to export")

        # Flatten: one row per glass
        flat = []
        all_oxides  = sorted({c["oxide"] for r in rows for c in r.get("compositions", [])})
        all_props   = sorted({p["property_name"] for r in rows for p in r.get("properties", [])})
        for r in rows:
            record = {"id": r["id"], "comp_type": r["comp_type"],
                      "comp_note": r.get("comp_note", ""), "comp_sum": r.get("comp_sum")}
            comp_map = {c["oxide"]: c["value"] for c in r.get("compositions", [])}
            for ox in all_oxides:
                record[ox] = comp_map.get(ox, "")
            prop_map = {p["property_name"]: p["value"] for p in r.get("properties", [])}
            for pn in all_props:
                record[pn] = prop_map.get(pn, "")
            flat.append(record)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=flat[0].keys())
        writer.writeheader()
        writer.writerows(flat)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name="zachv1_search.csv",
        )
    except Exception as e:
        logger.exception("export failed")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — CSV bulk glass import
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/add-glass/csv-template")
def api_csv_template():
    """Return a filled-in sample CSV so users know the exact format."""
    import io
    lines = [
        "name,source,notes,comp_type,SiO2,B2O3,Al2O3,Na2O,K2O,CaO,MgO,density,tg_celsius,refractive_index_nD",
        "Soda-lime standard,experimental,Reference glass,wt_pct,72.5,0,1.1,12.8,0.6,9.1,3.9,2.49,557,1.513",
        "Borosilicate 7740,literature,Corning 1936,wt_pct,80.5,12.0,2.5,4.0,1.0,0,0,2.23,525,1.474",
        "Aluminosilicate sample,experimental,,mol_pct,60.0,4.0,17.0,2.0,0,10.0,7.0,,,",
    ]
    content = "\n".join(lines)
    return send_file(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="zachv1_import_template.csv",
    )


@app.route("/api/add-glass/csv-preview", methods=["POST"])
def api_csv_preview():
    """Parse uploaded CSV and return a preview (no DB writes)."""
    try:
        if "file" not in request.files:
            return _err("No file — expected multipart field 'file'")
        text = request.files["file"].read().decode("utf-8", errors="replace")
        glasses, errors = db.parse_csv_glasses(text)
        return _ok({"glasses": glasses, "errors": errors,
                    "n_parsed": len(glasses), "n_errors": len(errors)})
    except Exception as e:
        logger.exception("csv-preview failed")
        return _err(str(e))


@app.route("/api/add-glass/csv-import", methods=["POST"])
def api_csv_import():
    """Parse and save all glasses from CSV upload."""
    try:
        if "file" not in request.files:
            return _err("No file — expected multipart field 'file'")
        text = request.files["file"].read().decode("utf-8", errors="replace")
        glasses, parse_errors = db.parse_csv_glasses(text)
        if not glasses:
            return _err(f"No valid glasses found. Errors: {parse_errors}")
        ids = db.bulk_save_glasses(glasses)
        return _ok({"saved": len(ids), "ids": ids, "parse_errors": parse_errors})
    except Exception as e:
        logger.exception("csv-import failed")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Similarity search
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/similar", methods=["POST"])
def api_similar():
    try:
        body = _parse_body()
        comp = {k: float(v) for k, v in body.get("composition", {}).items()
                if float(v) > 0}
        if not comp:
            return _err("composition required")
        results = db.find_similar_glasses(
            comp,
            n         = int(body.get("n", 15)),
            comp_type = body.get("comp_type", "mol_pct"),
        )
        return _ok(results)
    except Exception as e:
        logger.exception("similarity search failed")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Scatter / visualisation data
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/scatter", methods=["POST"])
def api_scatter():
    try:
        body       = _parse_body()
        x_type     = body.get("x_type", "oxide")    # "oxide" | "property"
        x_name     = body.get("x_name")
        y_prop     = body.get("y_prop")
        if not x_name or not y_prop:
            return _err("x_name and y_prop are required")
        data = db.get_scatter_data(
            x_type     = x_type,
            x_name     = x_name,
            y_prop     = y_prop,
            comp_type  = body.get("comp_type", "mol_pct"),
            color_prop = body.get("color_prop"),
            limit      = min(int(body.get("limit", 5000)), 10000),
        )
        return _ok(data)
    except Exception as e:
        logger.exception("scatter failed")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Batch predict from CSV
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/predict/csv", methods=["POST"])
def api_predict_csv():
    """Upload CSV of compositions, download CSV with ML predictions appended."""
    try:
        import io, csv
        from glasspy.ml import predict_batch

        if "file" not in request.files:
            return _err("No file — expected multipart field 'file'")

        text = request.files["file"].read().decode("utf-8", errors="replace")
        prop_names = request.form.get("prop_names", "density,tg_celsius,refractive_index_nD").split(",")
        prop_names = [p.strip() for p in prop_names if p.strip()]
        comp_type  = request.form.get("comp_type", "mol_pct")
        model_type = request.form.get("model_type", "random_forest")

        glasses, _ = db.parse_csv_glasses(text)
        if not glasses:
            return _err("No valid compositions found in CSV")

        compositions = [
            {c["oxide"]: c["value"] for c in g["compositions"]}
            for g in glasses
        ]
        predictions = predict_batch(compositions, prop_names,
                                    comp_type=comp_type, model_type=model_type)

        # Build output CSV
        out = io.StringIO()
        all_oxides = sorted({ox for comp in compositions for ox in comp})
        fieldnames = (["name", "source", "comp_type"] + all_oxides
                      + [f"pred_{p}" for p in prop_names]
                      + [f"pred_{p}_lower" for p in prop_names]
                      + [f"pred_{p}_upper" for p in prop_names])
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for i, (g, pred_row) in enumerate(zip(glasses, predictions)):
            comp_map = {c["oxide"]: c["value"] for c in g["compositions"]}
            record = {"name": g["name"], "source": g["source"],
                      "comp_type": g["compositions"][0].get("comp_type", comp_type)}
            record.update(comp_map)
            for p in prop_names:
                record[f"pred_{p}"]       = pred_row.get(p, "")
                record[f"pred_{p}_lower"] = pred_row.get(f"{p}_lower", "")
                record[f"pred_{p}_upper"] = pred_row.get(f"{p}_upper", "")
            writer.writerow(record)

        out.seek(0)
        return send_file(
            io.BytesIO(out.getvalue().encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name="zachv1_predictions.csv",
        )
    except Exception as e:
        logger.exception("predict/csv failed")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — User database management (export / import / delete)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/user-data/export-json")
def api_export_user_json():
    """Download all user glasses as a portable JSON backup."""
    try:
        import io
        data = db.export_user_db_json()
        payload = json.dumps(data, indent=2).encode("utf-8")
        return send_file(
            io.BytesIO(payload),
            mimetype="application/json",
            as_attachment=True,
            download_name="zachv1_user_database.json",
        )
    except Exception as e:
        return _err(str(e))


@app.route("/api/user-data/export-sqlite")
def api_export_user_sqlite():
    """Download the raw SQLite user-data file."""
    try:
        if not os.path.exists(USER_DB):
            return _err("No user database found", 404)
        return send_file(
            USER_DB,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name="zachv1_user_data.db",
        )
    except Exception as e:
        return _err(str(e))


@app.route("/api/user-data/import-json", methods=["POST"])
def api_import_user_json():
    """Import a JSON backup. multipart file upload expected under key 'file'.
    Optional query param ?mode=replace to wipe before import (default: merge).
    """
    try:
        if "file" not in request.files:
            return _err("No file uploaded — expected multipart field 'file'")
        f    = request.files["file"]
        mode = request.args.get("mode", "merge")
        data = json.loads(f.read().decode("utf-8"))
        if data.get("_format") != "zachv1_userdb":
            return _err("File does not look like a Zach V1 export (missing _format key)")
        result = db.import_user_db_json(data, mode=mode)
        return _ok(result)
    except json.JSONDecodeError:
        return _err("Invalid JSON — make sure you upload a Zach V1 .json export file")
    except Exception as e:
        logger.exception("import failed")
        return _err(str(e))


@app.route("/api/user-data/delete/<int:glass_id>", methods=["DELETE"])
def api_delete_user_glass(glass_id):
    """Permanently delete a user glass."""
    try:
        db.delete_user_glass(glass_id)
        return _ok({"deleted": glass_id})
    except Exception as e:
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# API — Contact (email links — client-side handled, this just validates)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/contact", methods=["POST"])
def api_contact():
    """Returns a mailto: link for the requested contact type."""
    body      = _parse_body()
    kind      = body.get("type", "consulting")
    name      = body.get("name", "")
    email     = body.get("email", "")
    message   = body.get("message", "")
    if kind == "consulting":
        subject = f"Consulting Call Request — {name}"
    else:
        subject = f"Glass Testing Service Request — {name}"
    import urllib.parse
    body_txt = f"From: {name} ({email})\n\n{message}"
    mailto = (f"mailto:gongyauc@gmail.com"
              f"?subject={urllib.parse.quote(subject)}"
              f"&body={urllib.parse.quote(body_txt)}")
    return _ok({"mailto": mailto})


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return _ok({
        "sciglass_db":    os.path.exists(DB_PATH),
        "user_db":        os.path.exists(USER_DB),
        "model_dir":      MODEL_DIR,
        "preload_status": _preload_status,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Error handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return _err("Not found", 404)
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return _err("Internal server error", 500)
    return render_template("500.html"), 500


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _start_preload()   # train / load cached models in background after startup
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG, use_reloader=False)
