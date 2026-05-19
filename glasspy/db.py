"""Database access layer — SciGlass clean DB + user data DB."""
import sqlite3, os, json
from contextlib import contextmanager
import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DB_PATH, USER_DB

@contextmanager
def sci_conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()

@contextmanager
def user_conn():
    con = sqlite3.connect(USER_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
    finally:
        con.close()

def init_user_db():
    with user_conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS user_glasses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            source      TEXT DEFAULT 'experimental',
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS user_compositions (
            glass_id    INTEGER,
            oxide       TEXT,
            value       REAL,
            comp_type   TEXT DEFAULT 'wt_pct',
            PRIMARY KEY (glass_id, oxide),
            FOREIGN KEY (glass_id) REFERENCES user_glasses(id)
        );
        CREATE TABLE IF NOT EXISTS user_properties (
            glass_id        INTEGER,
            property_name   TEXT,
            value           REAL,
            unit            TEXT,
            temperature     REAL,
            notes           TEXT,
            FOREIGN KEY (glass_id) REFERENCES user_glasses(id)
        );
        CREATE TABLE IF NOT EXISTS user_viscosity (
            glass_id    INTEGER,
            temperature REAL,
            log_visc    REAL,
            notes       TEXT,
            FOREIGN KEY (glass_id) REFERENCES user_glasses(id)
        );
        """)
        db.commit()

# ── SciGlass queries ──────────────────────────────────────────────────────────

def search_glasses(oxide_filters=None, prop_filters=None, comp_type=None,
                   limit=100, offset=0, sort_by="id", include_details=False):
    """Search glasses with optional composition and property filters.

    When include_details=True, each result also contains:
      compositions: [{oxide, value, comp_type}]
      properties:   [{property_name, value, unit}]
    """
    with sci_conn() as db:
        conditions = []
        params     = []

        # Use numbered aliases to avoid collisions (no string mangling)
        base = "SELECT DISTINCT g.id, g.comp_type, g.comp_note, g.comp_sum FROM glasses g"

        if oxide_filters:
            for i, (ox, lo, hi) in enumerate(oxide_filters):
                alias = f"cf{i}"
                base += (f" JOIN compositions {alias}"
                         f" ON {alias}.glass_id=g.id AND {alias}.oxide=?")
                params.append(ox)
                conditions.append(f"{alias}.value BETWEEN ? AND ?")
                params += [lo, hi]

        if prop_filters:
            for i, (pname, lo, hi) in enumerate(prop_filters):
                alias = f"pf{i}"
                base += (f" JOIN properties {alias}"
                         f" ON {alias}.glass_id=g.id AND {alias}.property_name=?"
                         f" AND {alias}.value_ok=1")
                params.append(pname)
                conditions.append(f"{alias}.value BETWEEN ? AND ?")
                params += [lo, hi]

        if comp_type:
            conditions.append("g.comp_type=?")
            params.append(comp_type)

        conditions.append("g.comp_valid=1")
        base += " WHERE " + " AND ".join(conditions)

        count_sql = f"SELECT COUNT(*) FROM ({base})"
        total = db.execute(count_sql, params).fetchone()[0]

        base += f" ORDER BY g.{sort_by} LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = [dict(r) for r in db.execute(base, params).fetchall()]

        if include_details and rows:
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))

            comp_rows = db.execute(
                f"SELECT glass_id, oxide, value, comp_type FROM compositions"
                f" WHERE glass_id IN ({placeholders}) ORDER BY value DESC",
                ids,
            ).fetchall()
            prop_rows = db.execute(
                f"SELECT glass_id, property_name, value, unit FROM properties"
                f" WHERE glass_id IN ({placeholders}) AND value_ok=1"
                f" ORDER BY property_name",
                ids,
            ).fetchall()

            from collections import defaultdict
            comp_map = defaultdict(list)
            for c in comp_rows:
                comp_map[c["glass_id"]].append(
                    {"oxide": c["oxide"], "value": c["value"], "comp_type": c["comp_type"]}
                )
            prop_map = defaultdict(list)
            for p in prop_rows:
                prop_map[p["glass_id"]].append(
                    {"property_name": p["property_name"],
                     "value": p["value"], "unit": p["unit"]}
                )
            for r in rows:
                r["compositions"] = comp_map[r["id"]]
                r["properties"]   = prop_map[r["id"]]

        return rows, total


def get_glass(glass_id, source="sciglass"):
    if source == "user":
        with user_conn() as db:
            g = db.execute("SELECT * FROM user_glasses WHERE id=?", (glass_id,)).fetchone()
            if not g: return None
            comps = db.execute("SELECT oxide, value, comp_type FROM user_compositions WHERE glass_id=?", (glass_id,)).fetchall()
            props = db.execute("SELECT property_name, value, unit, temperature, notes FROM user_properties WHERE glass_id=?", (glass_id,)).fetchall()
            visc  = db.execute("SELECT temperature, log_visc, notes FROM user_viscosity WHERE glass_id=? ORDER BY temperature", (glass_id,)).fetchall()
            return {
                "id": glass_id, "source": "user",
                "name": g["name"], "notes": g["notes"],
                "compositions": [dict(c) for c in comps],
                "properties": [dict(p) for p in props],
                "viscosity_points": [dict(v) for v in visc],
            }
    with sci_conn() as db:
        g = db.execute("SELECT * FROM glasses WHERE id=?", (glass_id,)).fetchone()
        if not g: return None
        comps = db.execute("SELECT oxide, value, comp_type FROM compositions WHERE glass_id=?", (glass_id,)).fetchall()
        props = db.execute("""
            SELECT property_name, value, unit, temperature_condition
            FROM properties WHERE glass_id=? AND value_ok=1
            ORDER BY property_name
        """, (glass_id,)).fetchall()
        return {
            "id": glass_id, "source": "sciglass",
            "comp_type": g["comp_type"],
            "comp_note": g["comp_note"],
            "compositions": [dict(c) for c in comps],
            "properties":   [dict(p) for p in props],
        }


def get_stats():
    with sci_conn() as db:
        n_glasses = db.execute("SELECT COUNT(*) FROM glasses").fetchone()[0]
        n_comps   = db.execute("SELECT COUNT(DISTINCT oxide) FROM compositions").fetchone()[0]
        n_props   = db.execute("SELECT SUM(value_ok) FROM properties").fetchone()[0]
        n_types   = db.execute("SELECT COUNT(DISTINCT comp_type) FROM glasses WHERE comp_valid=1").fetchone()[0]
    with user_conn() as db:
        n_user = db.execute("SELECT COUNT(*) FROM user_glasses").fetchone()[0]
    return dict(n_glasses=n_glasses, n_comp_types=n_comps,
                n_valid_props=n_props, n_user=n_user)


def get_property_stats(prop_name):
    with sci_conn() as db:
        r = db.execute("""
            SELECT COUNT(*), ROUND(MIN(value),3), ROUND(AVG(value),3),
                   ROUND(MAX(value),3), unit
            FROM properties WHERE property_name=? AND value_ok=1
        """, (prop_name,)).fetchone()
        if not r or not r[0]: return None
        return dict(n=r[0], min=r[1], avg=r[2], max=r[3], unit=r[4])


def save_user_glass(name, source, notes, compositions, properties, visc_points=None):
    with user_conn() as db:
        cur = db.execute(
            "INSERT INTO user_glasses (name, source, notes) VALUES (?,?,?)",
            (name, source, notes)
        )
        gid = cur.lastrowid
        for comp in compositions:
            db.execute(
                "INSERT INTO user_compositions VALUES (?,?,?,?)",
                (gid, comp["oxide"], comp["value"], comp.get("comp_type","wt_pct"))
            )
        for prop in properties:
            db.execute(
                "INSERT INTO user_properties (glass_id, property_name, value, unit, temperature, notes) VALUES (?,?,?,?,?,?)",
                (gid, prop["property_name"], prop["value"], prop.get("unit",""),
                 prop.get("temperature"), prop.get("notes",""))
            )
        if visc_points:
            for vp in visc_points:
                db.execute(
                    "INSERT INTO user_viscosity (glass_id, temperature, log_visc, notes) VALUES (?,?,?,?)",
                    (gid, vp["temperature"], vp["log_visc"], vp.get("notes",""))
                )
        db.commit()
    return gid


def list_user_glasses():
    with user_conn() as db:
        rows = db.execute("""
            SELECT g.id, g.name, g.source, g.notes, g.created_at,
                   COUNT(DISTINCT c.oxide) as n_oxides,
                   COUNT(DISTINCT p.property_name) as n_props
            FROM user_glasses g
            LEFT JOIN user_compositions c ON c.glass_id=g.id
            LEFT JOIN user_properties p ON p.glass_id=g.id
            GROUP BY g.id ORDER BY g.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_training_data(prop_name, comp_type=None, min_oxides=2):
    """Return (X_df, y_series) for ML training on a specific property."""
    import pandas as pd
    from config import OXIDES
    with sci_conn() as db:
        sql = """
            SELECT c.glass_id, c.oxide, c.value,
                   p.value as prop_value, g.comp_type
            FROM compositions c
            JOIN properties p ON p.glass_id=c.glass_id AND p.property_name=? AND p.value_ok=1
            JOIN glasses g ON g.id=c.glass_id
            WHERE g.comp_valid=1
        """
        params = [prop_name]
        if comp_type:
            sql += " AND g.comp_type=?"
            params.append(comp_type)
        rows = db.execute(sql, params).fetchall()

    if not rows:
        return None, None

    df = pd.DataFrame(rows, columns=["glass_id","oxide","value","prop_value","comp_type"])
    # Pivot compositions
    comp = df.pivot_table(index="glass_id", columns="oxide", values="value", aggfunc="first").fillna(0)
    # Keep only known oxides + add missing ones as 0
    for ox in OXIDES:
        if ox not in comp.columns:
            comp[ox] = 0.0
    comp = comp[OXIDES]

    prop = df.groupby("glass_id")["prop_value"].first()
    common_ids = comp.index.intersection(prop.index)
    return comp.loc[common_ids], prop.loc[common_ids]


def export_user_db_json():
    """Serialise the entire user database to a JSON-safe dict."""
    glasses = []
    with user_conn() as db:
        for g in db.execute("SELECT * FROM user_glasses ORDER BY id").fetchall():
            gid = g["id"]
            comps = db.execute(
                "SELECT oxide, value, comp_type FROM user_compositions WHERE glass_id=?",
                (gid,)).fetchall()
            props = db.execute(
                "SELECT property_name, value, unit, temperature, notes FROM user_properties WHERE glass_id=?",
                (gid,)).fetchall()
            visc  = db.execute(
                "SELECT temperature, log_visc, notes FROM user_viscosity WHERE glass_id=? ORDER BY temperature",
                (gid,)).fetchall()
            glasses.append({
                "name":             g["name"],
                "source":           g["source"],
                "notes":            g["notes"],
                "created_at":       g["created_at"],
                "compositions":     [dict(c) for c in comps],
                "properties":       [dict(p) for p in props],
                "viscosity_points": [dict(v) for v in visc],
            })
    return {"_format": "zachv1_userdb", "_version": "1.0",
            "n_glasses": len(glasses), "glasses": glasses}


def import_user_db_json(data, mode="merge"):
    """Import glasses from a JSON export.
    mode='merge'   — append all glasses (always adds, never deduplicates).
    mode='replace' — wipe existing user data first, then import.
    Returns dict with counts.
    """
    if mode == "replace":
        with user_conn() as db:
            db.execute("DELETE FROM user_viscosity")
            db.execute("DELETE FROM user_properties")
            db.execute("DELETE FROM user_compositions")
            db.execute("DELETE FROM user_glasses")
            db.commit()

    imported = 0
    errors   = []
    for g in data.get("glasses", []):
        try:
            save_user_glass(
                g.get("name", "Imported glass"),
                g.get("source", "imported"),
                g.get("notes", ""),
                g.get("compositions", []),
                g.get("properties", []),
                g.get("viscosity_points", []),
            )
            imported += 1
        except Exception as exc:
            errors.append(str(exc))

    return {"imported": imported, "errors": errors}


def delete_user_glass(glass_id):
    """Permanently remove a user glass and all its associated data."""
    with user_conn() as db:
        db.execute("DELETE FROM user_viscosity   WHERE glass_id=?", (glass_id,))
        db.execute("DELETE FROM user_properties  WHERE glass_id=?", (glass_id,))
        db.execute("DELETE FROM user_compositions WHERE glass_id=?", (glass_id,))
        db.execute("DELETE FROM user_glasses      WHERE id=?",       (glass_id,))
        db.commit()


def parse_csv_glasses(csv_text):
    """Parse CSV text into glass dicts ready for save_user_glass().

    Required column : name
    Optional meta   : source, notes, comp_type
    Oxide columns   : any oxide from OXIDES list (case-insensitive match)
    Property columns: any other column (treated as property name → float value)

    Returns (glasses_list, errors_list).
    """
    import csv, io
    from config import OXIDES

    OXIDE_SET  = {ox.upper(): ox for ox in OXIDES}   # upper→canonical
    META_COLS  = {"name", "source", "notes", "comp_type"}

    reader  = csv.DictReader(io.StringIO(csv_text.strip()))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    lower_h = [h.lower() for h in headers]

    if "name" not in lower_h:
        return [], ["CSV must contain a 'name' column."]

    # Classify columns
    oxide_map = {}   # csv_header → canonical oxide name
    prop_hdrs = []   # property column headers
    for h in headers:
        hl = h.strip().lower()
        if hl in META_COLS:
            continue
        canonical = OXIDE_SET.get(h.strip().upper())
        if canonical:
            oxide_map[h] = canonical
        else:
            prop_hdrs.append(h)

    glasses, errors = [], []
    for i, row in enumerate(reader, start=2):
        # Resolve name (case-insensitive)
        name = ""
        for hdr in headers:
            if hdr.lower() == "name":
                name = (row.get(hdr) or "").strip()
                break
        if not name:
            errors.append(f"Row {i}: empty name — skipped.")
            continue

        def _get(key):
            for hdr in headers:
                if hdr.lower() == key:
                    return (row.get(hdr) or "").strip()
            return ""

        comp_type_val = _get("comp_type") or "wt_pct"
        source_val    = _get("source")    or "csv_import"
        notes_val     = _get("notes")     or ""

        compositions = []
        for hdr, oxide in oxide_map.items():
            raw = (row.get(hdr) or "").strip()
            if not raw:
                continue
            try:
                v = float(raw)
                if v > 0:
                    compositions.append({"oxide": oxide, "value": v,
                                         "comp_type": comp_type_val})
            except ValueError:
                pass

        if not compositions:
            errors.append(f"Row {i} ({name}): no oxide data found — skipped.")
            continue

        properties = []
        for ph in prop_hdrs:
            raw = (row.get(ph) or "").strip()
            if not raw:
                continue
            try:
                v = float(raw)
                properties.append({"property_name": ph, "value": v, "unit": ""})
            except ValueError:
                pass

        glasses.append({
            "name":         name,
            "source":       source_val,
            "notes":        notes_val,
            "compositions": compositions,
            "properties":   properties,
        })

    return glasses, errors


def bulk_save_glasses(glasses_list):
    """Save a list of glass dicts (from parse_csv_glasses). Returns list of new IDs."""
    ids = []
    for g in glasses_list:
        gid = save_user_glass(
            g["name"], g["source"], g.get("notes", ""),
            g["compositions"], g.get("properties", []),
            g.get("viscosity_points", []),
        )
        ids.append(gid)
    return ids


def find_similar_glasses(composition, n=15, comp_type="mol_pct"):
    """Find the N most compositionally similar glasses using L2 distance.

    composition: {oxide: value} — will be normalised to 100%.
    Returns list of dicts sorted by ascending distance.
    """
    import math
    from collections import defaultdict

    # Normalise query composition to 100 %
    total = sum(v for v in composition.values() if v and v > 0)
    if total <= 0:
        return []
    norm = {ox: v / total * 100 for ox, v in composition.items() if v and v > 0}

    # Major oxides (top 3 by %) — used to pre-filter candidates
    major = sorted(norm.items(), key=lambda x: -x[1])[:3]
    major_oxides = [ox for ox, _ in major]

    with sci_conn() as db:
        ph = ",".join("?" * len(major_oxides))
        sql = f"""
            SELECT c.glass_id, c.oxide, c.value
            FROM compositions c
            JOIN glasses g ON g.id = c.glass_id
            WHERE g.comp_valid = 1
              AND g.comp_type  = ?
              AND c.glass_id IN (
                  SELECT glass_id FROM compositions
                  WHERE oxide IN ({ph}) AND value > 0
                  GROUP BY glass_id
                  HAVING COUNT(DISTINCT oxide) >= ?
              )
        """
        min_match = min(2, len(major_oxides))
        rows = db.execute(sql, [comp_type] + major_oxides + [min_match]).fetchall()

    # Pivot
    glass_comps = defaultdict(dict)
    for r in rows:
        glass_comps[r["glass_id"]][r["oxide"]] = r["value"]

    # Compute distances
    query_oxides = set(norm.keys())
    distances = []
    for gid, gcomp in glass_comps.items():
        dist_sq = sum((norm.get(ox, 0) - gcomp.get(ox, 0)) ** 2
                      for ox in query_oxides)
        # Penalise extra oxides in the candidate that are absent in query
        dist_sq += sum(v * v for ox, v in gcomp.items()
                       if ox not in norm and v > 1.0)
        distances.append((gid, math.sqrt(dist_sq)))

    distances.sort(key=lambda x: x[1])
    top = distances[:n]
    if not top:
        return []

    top_ids  = [gid for gid, _ in top]
    dist_map = {gid: d for gid, d in top}

    ph2 = ",".join("?" * len(top_ids))
    with sci_conn() as db:
        comp_rows = db.execute(
            f"SELECT glass_id, oxide, value, comp_type FROM compositions"
            f" WHERE glass_id IN ({ph2}) ORDER BY value DESC", top_ids).fetchall()
        prop_rows = db.execute(
            f"SELECT glass_id, property_name, value, unit FROM properties"
            f" WHERE glass_id IN ({ph2}) AND value_ok=1 ORDER BY property_name", top_ids).fetchall()

    comp_map = defaultdict(list)
    for c in comp_rows:
        comp_map[c["glass_id"]].append(
            {"oxide": c["oxide"], "value": c["value"], "comp_type": c["comp_type"]})
    prop_map = defaultdict(list)
    for p in prop_rows:
        prop_map[p["glass_id"]].append(
            {"property_name": p["property_name"], "value": p["value"], "unit": p["unit"]})

    # Similarity score: 100 = identical, 0 = very different (cap at dist=50)
    return [{
        "id":               gid,
        "distance":         round(dist_map[gid], 2),
        "similarity_pct":   round(max(0, 100 - dist_map[gid] * 2), 1),
        "compositions":     comp_map[gid],
        "properties":       prop_map[gid],
    } for gid in top_ids]


def get_scatter_data(x_type, x_name, y_prop, comp_type="mol_pct",
                     color_prop=None, limit=5000):
    """Return arrays suitable for a scatter plot.

    x_type : 'oxide'    → x_name is an oxide (e.g. 'SiO2')
             'property' → x_name is a property (e.g. 'tg_celsius')
    y_prop : property name for the Y axis
    color_prop : optional second property for colour
    """
    with sci_conn() as db:
        if x_type == "oxide":
            color_join = ""
            color_sel  = ""
            if color_prop:
                color_join = (f" LEFT JOIN properties pc"
                              f" ON pc.glass_id=g.id AND pc.property_name='{color_prop}'"
                              f" AND pc.value_ok=1")
                color_sel  = ", MAX(pc.value) as cv"
            sql = f"""
                SELECT g.id,
                       MAX(CASE WHEN c.oxide=? THEN c.value ELSE 0 END) as xv,
                       MAX(CASE WHEN py.property_name=? AND py.value_ok=1 THEN py.value END) as yv
                       {color_sel}
                FROM glasses g
                JOIN compositions c ON c.glass_id=g.id
                JOIN properties py  ON py.glass_id=g.id
                  AND py.property_name=? AND py.value_ok=1
                {color_join}
                WHERE g.comp_type=? AND g.comp_valid=1
                GROUP BY g.id
                HAVING xv > 0 AND yv IS NOT NULL
                ORDER BY RANDOM()
                LIMIT ?
            """
            rows = db.execute(sql, [x_name, y_prop, y_prop, comp_type, limit]).fetchall()
        else:
            color_join = ""
            color_sel  = ""
            if color_prop:
                color_join = (f" LEFT JOIN properties pc"
                              f" ON pc.glass_id=g.id AND pc.property_name='{color_prop}'"
                              f" AND pc.value_ok=1")
                color_sel  = ", MAX(pc.value) as cv"
            sql = f"""
                SELECT g.id,
                       MAX(CASE WHEN px.property_name=? AND px.value_ok=1 THEN px.value END) as xv,
                       MAX(CASE WHEN py.property_name=? AND py.value_ok=1 THEN py.value END) as yv
                       {color_sel}
                FROM glasses g
                JOIN properties px ON px.glass_id=g.id
                  AND px.property_name=? AND px.value_ok=1
                JOIN properties py ON py.glass_id=g.id
                  AND py.property_name=? AND py.value_ok=1
                {color_join}
                WHERE g.comp_valid=1 AND g.comp_type=?
                GROUP BY g.id
                HAVING xv IS NOT NULL AND yv IS NOT NULL
                ORDER BY RANDOM()
                LIMIT ?
            """
            rows = db.execute(sql, [x_name, y_prop, x_name, y_prop, comp_type, limit]).fetchall()

    result = {"ids": [], "x": [], "y": [], "c": []}
    for r in rows:
        result["ids"].append(r["id"])
        result["x"].append(r["xv"])
        result["y"].append(r["yv"])
        result["c"].append(r["cv"] if color_prop else None)
    return result


def get_ternary_data(ox1, ox2, ox3, prop_name, comp_type="mol_pct"):
    """Fetch data for a ternary property diagram."""
    with sci_conn() as db:
        sql = """
            SELECT g.id,
                   MAX(CASE WHEN c.oxide=? THEN c.value ELSE 0 END) as v1,
                   MAX(CASE WHEN c.oxide=? THEN c.value ELSE 0 END) as v2,
                   MAX(CASE WHEN c.oxide=? THEN c.value ELSE 0 END) as v3,
                   MAX(CASE WHEN p.property_name=? AND p.value_ok=1 THEN p.value END) as pv
            FROM glasses g
            JOIN compositions c ON c.glass_id=g.id
            LEFT JOIN properties p ON p.glass_id=g.id AND p.property_name=?
            WHERE g.comp_type=? AND g.comp_valid=1
            GROUP BY g.id
            HAVING v1>0 AND v2>0 AND v3>0 AND pv IS NOT NULL
            LIMIT 5000
        """
        rows = db.execute(sql, [ox1,ox2,ox3,prop_name,prop_name,comp_type]).fetchall()
    return [dict(r) for r in rows]
