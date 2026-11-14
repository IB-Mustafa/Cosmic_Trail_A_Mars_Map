"""Build the low-resolution elevation context used for the 3D globe.

Reads the local MOLA global DEM (Mars_MGS_MOLA_DEM_mosaic_global_463m.tif) once and
writes data/terrain_context.npz with:
  • regional — native 463 m MOLA around Gale (REGION), int16 metres
  • global   — MOLA averaged to 1/8° (GLOBAL_PX_DEG), int16 metres
Both are areoid-referenced heights like the HiRISE/USGS DTMs, planetocentric,
east-positive, on the IAU Mars sphere (R = 3 396 190 m).

The backend serves 3D terrain tiles from the analysis grid (5 m) where it exists and
from this context elsewhere (app/terrain_tiles.py). Without this file the globe stays flat.

Usage:  python scripts/build_terrain_context.py [path/to/MOLA.tif]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "terrain_context.npz"
MOLA_NAME = "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"
REGION = (131.0, -11.0, 144.0, 2.0)   # lon_min, lat_min, lon_max, lat_max (°)
GLOBAL_PX_DEG = 8                     # global grid: 8 px per degree = 0.125°


def find_mola() -> Path | None:
    for p in [ROOT / "data" / "raw" / MOLA_NAME, ROOT / "data" / "hirise_gale" / "raw" / MOLA_NAME]:
        if p.exists():
            return p
    return None


def deg_to_m(src, lon: float, lat: float) -> tuple[float, float]:
    # MOLA mosaic CRS is eqc lat_ts=0, lon_0=0 on R = 3 396 190 m.
    r = 3396190.0
    return np.radians(lon) * r, np.radians(lat) * r


def build(mola: Path) -> Path:
    t0 = time.time()
    with rasterio.open(mola) as src:
        nod = src.nodata
        # Regional window at native resolution.
        x0, y0 = deg_to_m(src, REGION[0], REGION[1])
        x1, y1 = deg_to_m(src, REGION[2], REGION[3])
        win = from_bounds(x0, y0, x1, y1, src.transform).round_offsets().round_lengths()
        regional = src.read(1, window=win)
        wt = src.window_transform(win)
        px_deg = src.res[0] / (np.radians(1) * 3396190.0)        # degrees per pixel
        reg_west = np.degrees(wt.c / 3396190.0)
        reg_north = np.degrees(wt.f / 3396190.0)
        print(f"regional {regional.shape} @ {px_deg:.5f}°/px, NW corner {reg_west:.4f}E {reg_north:.4f}N")

        # Global grid, averaged (reads the whole file once; ~2 GB).
        gw, gh = 360 * GLOBAL_PX_DEG, 180 * GLOBAL_PX_DEG
        glob = src.read(1, out_shape=(gh, gw), resampling=Resampling.average)
        print(f"global {glob.shape} in {time.time() - t0:.0f} s")

    for a in (regional, glob):
        if nod is not None:
            a[a == nod] = 0
    np.savez_compressed(
        OUT,
        regional=regional.astype(np.int16),
        regional_west=np.float64(reg_west), regional_north=np.float64(reg_north),
        regional_px_deg=np.float64(px_deg),
        global_=glob.astype(np.int16), global_px_deg=np.float64(1.0 / GLOBAL_PX_DEG),
        source=np.str_(f"{MOLA_NAME} (NASA GSFC MOLA Science Team / USGS, CC0)"),
    )
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
    return OUT


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_mola()
    if not path or not path.exists():
        sys.exit(f"MOLA DEM not found ({MOLA_NAME}). Pass its path as an argument.")
    build(path)
