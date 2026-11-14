"""Location context for ARIA and the route panel (offline, from bundled data only).

  geologic unit        → data/usgs_geologic_units.geojson (simplified SIM 3292 rectangles)
  dune / hazard zones  → data/hazard_zones.geojson (Polygon features, properties.kind == "dune").
                         Ships EMPTY: no verified Bagnold Dunes boundary is bundled yet, so
                         dune checks report "not loaded" instead of claiming "away from dunes".
  confirmed clay sites → CONFIRMED_CLAY_SITES (in-situ Curiosity results, cited)
  orbital minerals     → data/minerals/aqueous_minerals.json (Ehlmann & Edwards 2014)
  data quality         → the analysis grid's usgs_filled / mola_filled masks
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEOLOGY_FILE = DATA_DIR / "usgs_geologic_units.geojson"
HAZARD_ZONES_FILE = DATA_DIR / "hazard_zones.geojson"
MARS_R = 3396190.0
CAUTION_SLOPE_DEG = 10.0
NEAR_SITE_M = 5_000.0          # "route passes near" a science site
NEAR_DUNE_M = 500.0            # point counts as "near the dunes"

# In-situ clay confirmations inside the study area. Position: approximate waypoint from
# data/curiosity_official_route.geojson (~0.5 km NE of Bradbury Landing).
CONFIRMED_CLAY_SITES = [
    {"name": "Yellowknife Bay", "lon": 137.4453, "lat": -4.5890,
     "mineral": "smectite clays", "how": "Curiosity drill samples John Klein and Cumberland",
     "source": "Vaniman et al. 2014; Grotzinger et al. 2014", "coord_note": "approximate"},
]

GEO_AGE_WORDS = {"eHt": "Early Hesperian", "Htu": "Hesperian"}


# ---------------------------------------------------------------- geometry
def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * MARS_R * math.asin(math.sqrt(a))


def bearing_word(lon1: float, lat1: float, lon2: float, lat2: float) -> str:
    deg = math.degrees(math.atan2((lon2 - lon1) * math.cos(math.radians(lat1)), lat2 - lat1)) % 360
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][
        int((deg + 22.5) // 45) % 8]


def short_bearing(word: str) -> str:
    return {"north": "N", "north-east": "NE", "east": "E", "south-east": "SE", "south": "S",
            "south-west": "SW", "west": "W", "north-west": "NW"}[word]


def _in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _in_polygon(lon: float, lat: float, geom: dict) -> bool:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return any(_in_ring(lon, lat, p[0]) and not any(_in_ring(lon, lat, h) for h in p[1:]) for p in polys)


def _dist_to_polygon_m(lon: float, lat: float, geom: dict) -> float:
    """Distance to the polygon edge (0 inside), via vertex/segment sampling — fine at km scale."""
    if _in_polygon(lon, lat, geom):
        return 0.0
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    best = math.inf
    for p in polys:
        ring = p[0]
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            for t in np.linspace(0, 1, 21):
                best = min(best, distance_m(lon, lat, x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    return best


# ---------------------------------------------------------------- data files
@lru_cache(maxsize=1)
def _geology() -> dict | None:
    return json.loads(GEOLOGY_FILE.read_text(encoding="utf-8")) if GEOLOGY_FILE.exists() else None


@lru_cache(maxsize=1)
def _dunes() -> list[dict] | None:
    """Dune polygons, or None when no dune boundary data is bundled."""
    if not HAZARD_ZONES_FILE.exists():
        return None
    fc = json.loads(HAZARD_ZONES_FILE.read_text(encoding="utf-8"))
    dunes = [f for f in fc.get("features", []) if (f.get("properties") or {}).get("kind") == "dune"]
    return dunes or None


def geologic_unit(lon: float, lat: float) -> dict | None:
    g = _geology()
    for f in (g or {}).get("features", []):
        if _in_polygon(lon, lat, f["geometry"]):
            p = f["properties"]
            return {"unit": p["unit"], "name": p["name"], "age": p["age"],
                    "age_word": GEO_AGE_WORDS.get(p["unit"], p["age"])}
    return None


def dune_status(lon: float, lat: float) -> dict:
    dunes = _dunes()
    if dunes is None:
        return {"loaded": False}
    best = min(((_dist_to_polygon_m(lon, lat, f["geometry"]), f) for f in dunes), key=lambda t: t[0])
    props = best[1]["properties"]
    return {"loaded": True, "inside": best[0] == 0.0, "distance_m": round(best[0]),
            "name": props.get("name", "dune field"), "note": props.get("note"), "source": props.get("source")}


def dune_notes() -> list[dict]:
    """Thermal / crossing advice attached to the dune polygons (name, note, sources)."""
    return [{"name": f["properties"].get("name", "dune field"), "note": f["properties"].get("note"),
             "source": f["properties"].get("source"), "temperature_source": f["properties"].get("temperature_source")}
            for f in (_dunes() or []) if f["properties"].get("note")]


def dune_line(st: dict) -> str:
    if not st["loaded"]:
        return "dune map not loaded — sand not checked"
    tip = f" — {st['note']}" if st.get("note") else ""
    if st["inside"]:
        return f"⚠️ on {st['name']} sand (soft footing, bigger day–night temperature swings){tip}"
    if st["distance_m"] <= NEAR_DUNE_M:
        return f"⚠️ {st['name']} sand {st['distance_m']} m away{tip}"
    return f"away from dunes ({st['distance_m'] / 1000:.1f} km)"


def nearest_orbital_mineral(lon: float, lat: float, minerals: dict | None) -> dict | None:
    pts = (minerals or {}).get("points") or []
    if not pts:
        return None
    labels = {l["class"]: l["label"] for l in minerals.get("legend", [])}
    d, p = min(((distance_m(lon, lat, p["lon"], p["lat"]), p) for p in pts), key=lambda t: t[0])
    return {"label": labels.get(p["c"], p["c"]), "class": p["c"], "distance_m": round(d),
            "bearing": bearing_word(lon, lat, p["lon"], p["lat"]), "lon": p["lon"], "lat": p["lat"]}


def nearest_confirmed_clay(lon: float, lat: float) -> dict:
    d, s = min(((distance_m(lon, lat, s["lon"], s["lat"]), s) for s in CONFIRMED_CLAY_SITES), key=lambda t: t[0])
    return {**s, "distance_m": round(d), "bearing": bearing_word(lon, lat, s["lon"], s["lat"])}


def is_clay(mineral_class: str, label: str) -> bool:
    t = f"{mineral_class} {label}".lower()
    return any(k in t for k in ("clay", "phyllosilicate", "smectite", "kaolin", "chlorite", "prehnite"))


# ---------------------------------------------------------------- grid sampling
def source_at(ds, r: int, c: int) -> str:
    if ds.usgs_filled is not None and ds.usgs_filled[r, c]:
        return "usgs"
    if ds.mola_filled is not None and ds.mola_filled[r, c]:
        return "mola"
    return "hirise"


def line_profile(ds, lon0: float, lat0: float, lon1: float, lat1: float) -> dict:
    """Slopes along the straight line between two points, at grid resolution (inside the grid only)."""
    x0, y0 = ds.proj.forward(lon0, lat0)
    x1, y1 = ds.proj.forward(lon1, lat1)
    length = math.hypot(x1 - x0, y1 - y0)
    n = max(2, int(length / ds.grid.cell) + 1)
    slopes, fracs = [], []
    for i in range(n):
        t = i / (n - 1)
        rc = ds.grid.rc(x0 + t * (x1 - x0), y0 + t * (y1 - y0))
        if rc is None:
            continue
        s = float(ds.slope[rc])
        if math.isfinite(s):
            slopes.append(s)
            fracs.append(t)
    out = {"length_m": round(length), "sampled": len(slopes), "covered_fraction": len(slopes) / n}
    if not slopes:
        return out
    arr = np.array(slopes)
    over = arr > CAUTION_SLOPE_DEG
    runs = int(np.sum(over[1:] & ~over[:-1]) + (1 if over[0] else 0))
    k = int(arr.argmax())
    out.update(mean_deg=round(float(arr.mean()), 1), max_deg=round(float(arr.max()), 1),
               steep_sections=runs, steepest_at=fracs[k])
    return out


def where_word(frac: float) -> str:
    return "near the start" if frac < 0.33 else ("about halfway" if frac < 0.67 else "near the end")


def terrain_word(mean_deg: float) -> str:
    return "Flat plain" if mean_deg < 3 else ("Gently rolling ground" if mean_deg < 6 else "Rough, hilly ground")


# ---------------------------------------------------------------- route context
def route_context(ds, route: dict, minerals: dict | None) -> dict:
    """Science / thermal / data-quality notes for a computed route (shown under the route panel)."""
    xy = route.get("xy") or []
    lonlat = route.get("lonlat") or []
    counts = {"hirise": 0, "usgs": 0, "mola": 0}
    for x, y in xy:
        rc = ds.grid.rc(x, y)
        if rc is not None:
            counts[source_at(ds, *rc)] += 1
    total = max(1, sum(counts.values()))
    hirise_pct = round(100 * counts["hirise"] / total)

    # Science: closest approach to a confirmed clay site, and to an orbital clay detection.
    sample = lonlat[:: max(1, len(lonlat) // 400)] + lonlat[-1:] if lonlat else []
    science = None
    if sample:
        site, d_site = None, math.inf
        for s in CONFIRMED_CLAY_SITES:
            d = min(distance_m(lo, la, s["lon"], s["lat"]) for lo, la in sample)
            if d < d_site:
                site, d_site = s, d
        orb = None
        pts = [p for p in (minerals or {}).get("points") or []
               if is_clay(p["c"], {l["class"]: l["label"] for l in minerals.get("legend", [])}.get(p["c"], ""))]
        if pts:
            mid = sample[len(sample) // 2]
            near_pts = sorted(pts, key=lambda p: distance_m(mid[0], mid[1], p["lon"], p["lat"]))[:5]
            orb = min(min(distance_m(lo, la, p["lon"], p["lat"]) for lo, la in sample) for p in near_pts)
        if d_site <= NEAR_SITE_M:
            science = {"text": f"🔬 Science: route passes {d_site / 1000:.1f} km from {site['name']} "
                               f"(clay confirmed by Curiosity)", "site": site["name"], "distance_m": round(d_site)}
        elif orb is not None and orb <= NEAR_SITE_M:
            science = {"text": f"🔬 Science: route passes {orb / 1000:.1f} km from an orbital clay detection site",
                       "distance_m": round(orb)}
        else:
            nearest = min(d_site, orb if orb is not None else math.inf)
            science = {"text": f"🔬 Science: no clay site near this route (closest {nearest / 1000:.1f} km)",
                       "distance_m": round(nearest)}

    # Thermal / footing: dune crossings (needs dune boundary data).
    dunes = _dunes()
    if dunes is None:
        thermal = {"text": "🌡️ Thermal: dune map not loaded — dune crossings not checked", "checked": False}
    else:
        hit = [(lo, la) for lo, la in sample if any(_in_polygon(lo, la, f["geometry"]) for f in dunes)]
        if hit:
            frac = len(hit) / len(sample)
            names = sorted({f["properties"].get("name", "dune sand") for f in dunes
                            if any(_in_polygon(lo, la, f["geometry"]) for lo, la in hit)})
            notes = [f["properties"]["note"] for f in dunes if f["properties"].get("note")
                     and f["properties"].get("name", "dune sand") in names]
            thermal = {"text": f"🌡️ Thermal: crosses {', '.join(names)} on ~{frac * 100:.0f}% of the route — HIGH risk"
                               + (f". {notes[0]}" if notes else " (soft footing, larger day–night temperature swings)"),
                       "checked": True, "crossings": True, "dunes": names, "fraction": round(frac, 2)}
        else:
            thermal = {"text": "🌡️ Thermal: no dune crossings — LOW risk", "checked": True, "crossings": False}

    fill_note = (f" ({100 - hirise_pct}% USGS gap fill)" if counts["usgs"] else "") + \
                (" incl. MOLA fill" if counts["mola"] else "")
    return {
        "science": science,
        "thermal": thermal,
        "data": {"text": f"📡 Data: {hirise_pct}% HiRISE coverage along route{fill_note}",
                 "hirise_pct": hirise_pct, "cells": counts},
    }
