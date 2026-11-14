"""Build the bundled Mars place-label file for the frontend globe.

Source: IAU/USGS Gazetteer of Planetary Nomenclature — Mars feature centre points
(MARS_nomenclature_center_pts.zip), downloaded manually from
https://planetarynames.wr.usgs.gov/GIS_Downloads

Usage:
    python scripts/build_mars_labels.py path/to/MARS_nomenclature_center_pts.zip

Writes frontend/src/data/mars_labels.json so the app needs no network for labels.

Coordinate convention
---------------------
The gazetteer gives planetocentric latitude and 0–360° east-positive longitude on the
IAU Mars sphere (R = 3 396 190 m). The rest of COSMIC TRAIL (HiRISE DTMs, analysis
grid, Mars Trek basemap, Cesium globe) uses planetocentric latitude and east-positive
longitude in −180…180°, so the only conversion is lon > 180 → lon − 360.
"""
from __future__ import annotations

import datetime as dt
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "src" / "data" / "mars_labels.json"
DBF = "MARS_nomenclature_center_pts.dbf"


def _decode(raw: bytes) -> str:
    # The .cpg says UTF-8, but a few records contain Latin-1 bytes.
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("latin-1").strip()


def read_dbf(b: bytes) -> list[dict]:
    n, hlen, rlen = struct.unpack("<xxxxIHH", b[:12])
    fields, off = [], 32
    while b[off] != 0x0D:
        name = b[off:off + 11].split(b"\0")[0].decode("ascii")
        fields.append((name, chr(b[off + 11]), b[off + 16]))
        off += 32
    rows = []
    for i in range(n):
        rec = b[hlen + i * rlen: hlen + (i + 1) * rlen]
        if rec[:1] == b"*":  # deleted record
            continue
        p, row = 1, {}
        for name, ftype, flen in fields:
            raw = rec[p:p + flen]
            p += flen
            if ftype in "NF":
                try:
                    row[name] = float(raw.decode("ascii").strip())
                except ValueError:
                    row[name] = None
            else:
                row[name] = _decode(raw)
        rows.append(row)
    return rows


def short_type(t: str) -> str:
    # "Crater, craters" -> "Crater"; "Albedo Feature" stays.
    return t.split(",")[0].strip()


def main(zip_path: str) -> None:
    rows = read_dbf(zipfile.ZipFile(zip_path).read(DBF))
    features = []
    for r in rows:
        lat, lon = r["center_lat"], r["center_lon"]
        if lat is None or lon is None:
            continue
        if lon > 180:
            lon -= 360
        features.append({
            "n": r["name"],
            "t": short_type(r["type"]),
            "d": round(r["diameter"] or 0.0, 3),       # km
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "id": int(r["link"].rstrip("/").rsplit("/", 1)[-1]) if r.get("link") else None,
        })
    # Largest first: the label renderer places labels in this order.
    features.sort(key=lambda f: -f["d"])
    out = {
        "source": "IAU/USGS Gazetteer of Planetary Nomenclature — Mars feature centre points",
        "source_url": "https://planetarynames.wr.usgs.gov/GIS_Downloads",
        "feature_url": "https://planetarynames.wr.usgs.gov/Feature/{id}",
        "convention": "planetocentric latitude, east-positive longitude -180..180, IAU Mars sphere R=3396190 m",
        "built": dt.date.today().isoformat(),
        "count": len(features),
        "features": features,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(features)} features -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
