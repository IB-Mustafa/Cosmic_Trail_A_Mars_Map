"""Bundle the global aqueous-mineral detection points for the minerals layer.

Source: NASA Mars Trek product "Aqueous Mineral Distribution"
  (feature service .../trekarcgis/rest/services/Aquieous_Mineral_Distribution_Options_clon0/MapServer/0)
  compiled by Ehlmann, B. L. & Edwards, C. S. (2014), "Mineralogy of the Martian Surface",
  Annu. Rev. Earth Planet. Sci. 42:291–315 — detections from MRO CRISM, Mars Express
  OMEGA and Mars Odyssey THEMIS.

This is a SUMMARY COMPILATION of published detection locations (one point per site,
~0.01° precision), not a pixel-level CRISM mineral map.

Usage:  python scripts/build_mineral_points.py
Writes data/minerals/aqueous_minerals.json (read by GET /api/layers/minerals).
Coordinates: planetocentric latitude, east-positive longitude −180…180, Mars 2000 sphere.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "minerals" / "aqueous_minerals.json"
SERVICE = ("https://trek.nasa.gov/mars/trekarcgis/rest/services/"
           "Aquieous_Mineral_Distribution_Options_clon0/MapServer/0")   # (sic) "Aquieous" in NASA's URL
PAGE = 1000

# Class labels as described by the product (Mars Trek layer description).
CLASS_LABELS = {
    "phyllosilicate": "Phyllosilicates (clay minerals)",
    "sulfate": "Sulfates",
    "silica": "Silica (opaline / hydrated silica)",
    "chloride": "Chlorides",
    "carbonate": "Carbonates",
}


def query(params: dict) -> dict:
    q = urllib.parse.urlencode({**params, "f": "json"})
    req = urllib.request.Request(f"{SERVICE}/query?{q}", headers={"User-Agent": "cosmic-trail-data-builder"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def main() -> None:
    # The service supports neither result paging nor POST, so read all object IDs and
    # then fetch in FID ranges (each below the 1000-record limit).
    ids = sorted(query({"where": "1=1", "returnIdsOnly": "true"})["objectIds"])
    rows = []
    for i in range(0, len(ids), PAGE):
        lo, hi = ids[i], ids[min(i + PAGE, len(ids)) - 1]
        data = query({"where": f"FID >= {lo} AND FID <= {hi}",
                      "outFields": "Class,Longitude,Latitude,jC_fillclr", "returnGeometry": "false"})
        rows += [f["attributes"] for f in data.get("features", [])]
    print(f"downloaded {len(rows)} of {len(ids)} records")
    if len(rows) != len(ids):
        raise SystemExit("incomplete download — not writing the file")

    seen, points, colours = set(), [], {}
    for a in rows:
        cls = (a.get("Class") or "").strip().lower()
        lon, lat = a.get("Longitude"), a.get("Latitude")
        if not cls or lon is None or lat is None:
            continue
        lon = ((float(lon) + 180) % 360) - 180
        key = (cls, round(lon, 3), round(float(lat), 3))
        if key in seen:            # the service returns each site twice
            continue
        seen.add(key)
        points.append({"c": cls, "lon": round(lon, 3), "lat": round(float(lat), 3)})
        if a.get("jC_fillclr"):
            r, g, b, *_ = (int(v) for v in a["jC_fillclr"].split())
            colours.setdefault(cls, f"#{r:02x}{g:02x}{b:02x}")

    legend = [{"class": c, "label": CLASS_LABELS.get(c, c.title()), "color": colours.get(c, "#cccccc"),
               "count": sum(1 for p in points if p["c"] == c)} for c in sorted(colours)]
    out = {
        "title": "Aqueous mineral detections (global compilation)",
        "citation": "Ehlmann, B. L. & Edwards, C. S. (2014). Mineralogy of the Martian Surface. "
                    "Annu. Rev. Earth Planet. Sci. 42:291-315.",
        "instruments": ["MRO CRISM", "Mars Express OMEGA", "Mars Odyssey THEMIS"],
        "attribution": "NASA Mars Trek; data compiled by Ehlmann & Edwards (2014) from CRISM, OMEGA and THEMIS",
        "source_service": SERVICE,
        "retrieved": dt.date.today().isoformat(),
        "nature": "Summary compilation of published detection sites (one point per site, ~0.01 deg). "
                  "Not a pixel-level mineral map; absence of a point does not mean absence of the mineral.",
        "convention": "planetocentric latitude, east-positive longitude -180..180, Mars 2000 sphere",
        "legend": legend,
        "points": points,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(points)} unique points -> {OUT} ({OUT.stat().st_size // 1024} KB)")
    for l in legend:
        print(f"  {l['class']:15} {l['color']}  {l['count']}")


if __name__ == "__main__":
    main()
