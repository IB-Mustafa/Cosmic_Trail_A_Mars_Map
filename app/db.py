"""SQLite plan storage for COSMIC TRAIL.

Plans are stored locally on disk — no network required.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "plans.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS plans (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    dataset_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    start_lon   REAL,
    start_lat   REAL,
    end_lon     REAL,
    end_lat     REAL,
    route_mode  TEXT,
    route_data  TEXT,     -- JSON
    params      TEXT,     -- JSON
    notes       TEXT
);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(CREATE_SQL)
        conn.commit()
        yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("route_data", "params"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    return d


def list_plans() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, dataset_id, created_at, updated_at, route_mode, notes "
            "FROM plans ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_plan(plan_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_plan(name: str, dataset_id: str,
                start_lon: float | None = None, start_lat: float | None = None,
                end_lon: float | None = None, end_lat: float | None = None,
                route_mode: str | None = None, route_data: dict | None = None,
                params: dict | None = None, notes: str | None = None) -> dict:
    plan_id = str(uuid.uuid4())
    now = _now()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO plans
               (id, name, dataset_id, created_at, updated_at,
                start_lon, start_lat, end_lon, end_lat,
                route_mode, route_data, params, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (plan_id, name, dataset_id, now, now,
             start_lon, start_lat, end_lon, end_lat,
             route_mode,
             json.dumps(route_data) if route_data else None,
             json.dumps(params) if params else None,
             notes),
        )
        conn.commit()
    return get_plan(plan_id)


def update_plan(plan_id: str, **kwargs) -> dict | None:
    allowed = {"name", "start_lon", "start_lat", "end_lon", "end_lat",
               "route_mode", "route_data", "params", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_plan(plan_id)
    sets = []
    vals = []
    for k, v in updates.items():
        sets.append(f"{k}=?")
        if k in ("route_data", "params") and isinstance(v, dict):
            vals.append(json.dumps(v))
        else:
            vals.append(v)
    sets.append("updated_at=?")
    vals.append(_now())
    vals.append(plan_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE plans SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    return get_plan(plan_id)


def delete_plan(plan_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM plans WHERE id=?", (plan_id,))
        conn.commit()
        return cur.rowcount > 0


ROUTE_LABELS = {"terrain": "Terrain-safe route", "shortest": "Shortest route"}
_DISCLAIMER = "COSMIC TRAIL prototype — not for real EVA or rover operations."


def _plain(text: str) -> str:
    """Drop the emoji the UI puts in front of context lines (🔬, 🌡️, 📡 …)."""
    return "".join(ch for ch in text if ord(ch) < 0x2190 or 0x2200 <= ord(ch) < 0x2300).strip()


def _route_order(rd: dict, active: str | None) -> list[str]:
    modes = [m for m in ("terrain", "shortest") if rd.get(m)]
    if active in modes:
        modes.remove(active)
        modes.insert(0, active)
    return modes


def _distances_m(route: dict) -> list[float] | None:
    """Cumulative planimetric distance along the route, from its local-metre xy."""
    xy = route.get("xy")
    if not xy:
        return None
    out, d = [0.0], 0.0
    for (x0, y0), (x1, y1) in zip(xy, xy[1:]):
        d += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        out.append(round(d, 1))
    return out


def export_geojson(plan: dict) -> dict:
    """Convert a plan to a GeoJSON FeatureCollection (planetocentric lon/lat).

    Route vertices carry elevation as the third coordinate ([lon, lat, elevation_m],
    areoid-referenced metres as in the HiRISE DTMs) whenever every vertex has one.
    """
    features = []
    rd = plan.get("route_data") or {}
    active = plan.get("active_mode")
    for mode_key in _route_order(rd, active):
        route = rd[mode_key]
        if not route.get("lonlat"):
            continue
        lonlat = route["lonlat"]
        elev = route.get("elevation_profile") or []
        has_z = len(elev) == len(lonlat) and all(isinstance(e, (int, float)) for e in elev)
        coords = ([[round(lon, 7), round(lat, 7), round(float(e), 2)] for (lon, lat), e in zip(lonlat, elev)]
                  if has_z else [[round(lon, 7), round(lat, 7)] for lon, lat in lonlat])
        props = {
            "mode": mode_key,
            "name": ROUTE_LABELS.get(mode_key, mode_key),
            "active": mode_key == active if active else None,
            "planimetric_length_m": route.get("planimetric_length_m"),
            "geodesic_length_m": route.get("geodesic_length_m"),
            "surface_length_3d_m": route.get("surface_length_3d_m"),
            "elevation_gain_m": route.get("elevation_gain_m"),
            "elevation_loss_m": route.get("elevation_loss_m"),
            "elevation_start_m": route.get("elevation_start_m"),
            "elevation_end_m": route.get("elevation_end_m"),
            "elevation_min_m": route.get("elevation_min_m"),
            "elevation_max_m": route.get("elevation_max_m"),
            "slope_mean_deg": route.get("slope_mean_deg"),
            "slope_p90_deg": route.get("slope_p90_deg"),
            "slope_max_deg": route.get("slope_max_deg"),
            "cells_above_caution": route.get("cells_above_caution"),
            "data_coverage_on_route": route.get("data_coverage_on_route"),
            "warnings": [w.get("text", "") for w in route.get("warnings") or []],
            "coordinate_order": "lon, lat, elevation_m" if has_z else "lon, lat",
            "slope_profile_deg": route.get("slope_profile"),
            "distance_along_m": _distances_m(route),
            "note": "Coordinates are Mars planetocentric (lon_E, lat). "
                    "Routing is a prototype — not for real EVA or rover use.",
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {k: v for k, v in props.items() if v is not None},
        })
    # Start/end markers
    for label, lon, lat in [
        ("start", plan.get("start_lon"), plan.get("start_lat")),
        ("destination", plan.get("end_lon"), plan.get("end_lat")),
    ]:
        if lon is not None and lat is not None:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"label": label},
            })
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "plan_id": plan.get("id"),
            "plan_name": plan.get("name"),
            "dataset_id": plan.get("dataset_id"),
            "created_at": plan.get("created_at"),
            "crs": "Mars planetocentric, lon positive east, IAU sphere R = 3 396 190 m",
            "elevation": "metres, areoid-referenced (as in the HiRISE DTMs)",
            "params_used": rd.get("params_used"),
            "disclaimer": _DISCLAIMER,
        },
    }


def _fmt(v, unit: str = "", nd: int = 1) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, (int, float)):
        return f"{v:,.{nd}f}{unit}"
    return f"{v}{unit}"


def _fmt_lonlat(lon, lat) -> str:
    if lon is None or lat is None:
        return "n/a"
    return f"{abs(lat):.5f}°{'S' if lat < 0 else 'N'}, {abs(lon):.5f}°{'W' if lon < 0 else 'E'}"


def _data_sources(meta: dict) -> list[str]:
    lines = ["DATA SOURCES", "------------"]
    prov = meta.get("provenance") or {}
    dtms = [prov.get("primary_source")] + list(prov.get("additional_sources") or [])
    dtms = [d for d in dtms if d]
    if dtms:
        lines.append("  Elevation (routing grid, resampled to 5 m):")
        for d in dtms:
            pair = " + ".join(d.get("stereo_pair") or [])
            lines.append(f"    • HiRISE DTM {d.get('product_id', 'n/a')}"
                         + (f" ({pair}, {d.get('post_spacing_m', 'n/a')} m posts)" if pair else ""))
        credit = dtms[0].get("credit")
        if credit:
            lines.append(f"      Credit: {credit}. Terms: {dtms[0].get('terms', 'n/a')}")
    fill = meta.get("usgs_fill") or {}
    if fill.get("available"):
        lines.append(f"  Gap fill: {fill.get('source', 'n/a')} ({fill.get('resolution_m', 'n/a')} m), "
                     f"credit {fill.get('credit', 'n/a')}")
    elif meta.get("fill_source") == "mola":
        lines.append("  Gap fill: MOLA 463 m global DEM (NASA GSFC / USGS)")
    ortho = meta.get("ortho") or {}
    if ortho.get("available") and ortho.get("sources"):
        lines.append(f"  Imagery (display only): HiRISE orthoimages {', '.join(s[:15] for s in ortho['sources'])}, "
                     f"credit {ortho.get('credit', 'n/a')}")
    lines.append("  Coordinates: planetocentric latitude, east-positive longitude, IAU Mars sphere.")
    lines.append("")
    return lines


def export_briefing(plan: dict, dataset_meta: dict | None = None) -> str:
    """Plain-text mission briefing."""
    rd = plan.get("route_data") or {}
    params = rd.get("params_used") or {}
    caution = params.get("caution_slope_deg")
    max_slope = params.get("max_slope_deg")
    lines = [
        "═══════════════════════════════════════════════════════════",
        "COSMIC TRAIL — MISSION BRIEFING",
        "═══════════════════════════════════════════════════════════",
        f"Plan:        {plan.get('name', 'Unnamed')}",
    ]
    if plan.get("id"):
        lines.append(f"ID:          {plan.get('id')}")
    lines += [
        f"Dataset:     {plan.get('dataset_id')}",
        f"Created:     {plan.get('created_at')}",
        f"Start (A):   {_fmt_lonlat(plan.get('start_lon'), plan.get('start_lat'))}",
        f"Destination: {_fmt_lonlat(plan.get('end_lon'), plan.get('end_lat'))}",
        "",
        "DISCLAIMER",
        "----------",
        "This is a prototype terrain analysis output, not an engineering",
        "document. No route here is certified safe for real EVA or rover use.",
        "Slope thresholds are based on Apollo EVA traverses and NASA MSL Engineering User Guide thresholds. See SCIENTIFIC_LIMITATIONS.md.",
        "",
    ]
    if plan.get("notes"):
        lines += ["NOTES", "-----", plan["notes"], ""]
    if params:
        lines += [
            "ROUTING PARAMETERS",
            "------------------",
            f"  Caution slope:         {_fmt(caution, ' deg')}",
            f"  Maximum slope:         {_fmt(max_slope, ' deg')} (steeper cells are impassable)",
            "",
        ]
    active = plan.get("active_mode")
    for mode_key in _route_order(rd, active):
        r = rd[mode_key]
        label = ("Shortest Route" if mode_key == "shortest" else "Terrain-Weighted Route")
        if active:
            label = ROUTE_LABELS[mode_key] + (" (selected)" if mode_key == active else "")
        lines += [
            label.upper(),
            "-" * len(label),
            f"  Length (planimetric):  {_fmt(r.get('planimetric_length_m'), ' m')}",
            f"  Length (geodesic):     {_fmt(r.get('geodesic_length_m'), ' m')}",
            f"  Length (3D surface):   {_fmt(r.get('surface_length_3d_m'), ' m')}",
            f"  Elevation start / end: {_fmt(r.get('elevation_start_m'), ' m')} / {_fmt(r.get('elevation_end_m'), ' m')}",
            f"  Elevation min / max:   {_fmt(r.get('elevation_min_m'), ' m')} / {_fmt(r.get('elevation_max_m'), ' m')}",
            f"  Elevation gain:        {_fmt(r.get('elevation_gain_m'), ' m')}",
            f"  Elevation loss:        {_fmt(r.get('elevation_loss_m'), ' m')}",
            f"  Slope (mean / max):    {_fmt(r.get('slope_mean_deg'), ' deg')} / {_fmt(r.get('slope_max_deg'), ' deg')}",
            f"  Slope (90th pct):      {_fmt(r.get('slope_p90_deg'), ' deg')}",
            f"  Cells above caution:   {r.get('cells_above_caution', 'n/a')}",
        ]
        if r.get("data_coverage_on_route") is not None:
            lines.append(f"  Data coverage:         {r['data_coverage_on_route'] * 100:.0f}% of route cells")
        # Where the steepest cell is, along the route.
        slopes, dist = r.get("slope_profile") or [], _distances_m(r)
        valid = [(s, i) for i, s in enumerate(slopes) if isinstance(s, (int, float))]
        if valid and dist and len(dist) == len(slopes):
            s, i = max(valid)
            lines.append(f"  Steepest point:        {s:.1f} deg at {dist[i] / 1000:.2f} km from start")
        ctx = r.get("context") or {}
        ctx_lines = [_plain(ctx[k]["text"]) for k in ("science", "thermal", "data") if ctx.get(k) and ctx[k].get("text")]
        if ctx_lines:
            lines.append("  Context:")
            lines += [f"    • {t}" for t in ctx_lines]
        if r.get("warnings"):
            lines.append("  Warnings:")
            for w in r["warnings"]:
                lines.append(f"    • {w.get('text', '')}")
        else:
            lines.append("  Warnings:              none")
        lines.append("")
    if rd.get("tradeoff_summary"):
        lines += ["TRADE-OFF", "---------", rd["tradeoff_summary"], ""]
    if dataset_meta:
        lines += _data_sources(dataset_meta)
        lines += [
            "DATASET PROVENANCE",
            "------------------",
        ]
        prov = dataset_meta.get("provenance", {})
        src = prov.get("primary_source", {})
        if src:
            lines.append(f"  Product:  {src.get('product_id', 'n/a')}")
            lines.append(f"  Credit:   {src.get('credit', 'n/a')}")
            lines.append(f"  Terms:    {src.get('terms', 'n/a')}")
        lines.append(f"  Kind:     {dataset_meta.get('kind', 'n/a')}")
        lines.append("")
    lines.append("═══════════════════════════════════════════════════════════")
    return "\n".join(lines)
