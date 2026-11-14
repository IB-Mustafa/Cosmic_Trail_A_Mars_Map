"""Merge the HiRISE ortho photos over the study area into one clipped GeoTIFF.

Output: data/hirise_gale/ortho_mosaic.tif — 8-bit greyscale, 0 = no data, ~1 m pixels,
clipped exactly to the study window (default 137.35–137.55°E, 4.75–4.45°S), tiled,
DEFLATE-compressed, with internal overviews. The backend cuts globe imagery tiles from it
(app/ortho_tiles.py → GET /api/datasets/hirise_gale/ortho/{z}/{x}/{y}.png).

CRS: equidistant cylindrical with lat_ts = 0, lon_0 = window centre, on the IAU Mars
sphere R = 3 396 190 m — linear in planetocentric lon/lat, so the pixel-edge bounds are
exactly the lon/lat window (same convention as every other layer, see frontend/src/mars.ts).

Mosaic:
  * Priority order (ORTHO_FILES): the first image wins where images overlap; later images
    only fill pixels that are still empty.
  * Tone: each image is histogram-matched to the pooled histogram of all of them, so the
    strips (taken years apart, under different sun angles) meet at similar brightness.
    The display contrast curve is applied later, per tile, by the backend.
  * A 1-px rim is dropped at each image's no-data edge (bilinear resampling blends the
    black collar into it).

Usage:
    python scripts/build_ortho_mosaic.py                # uses data/hirise_gale/raw/
    python scripts/build_ortho_mosaic.py --res 2        # 2 m pixels (smaller file)

Also called from scripts/prepare_data.py after the orthos are downloaded.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "hirise_gale"
RAW_DIRS = [OUT_DIR / "raw", ROOT / "data" / "raw"]
MARS_R = 3396190.0
STUDY_WINDOW = (137.35, 137.55, -4.75, -4.45)   # lon_min, lon_max, lat_min, lat_max
MOSAIC_NAME = "ortho_mosaic.tif"
CREDIT = "NASA/JPL-Caltech/UArizona"

# HiRISE RED orthoimages (1 m) of the DTM pairs that cover the study window, in priority order.
# Orbits before ~011000 are the PSP mission phase, hence the PSP_ prefix.
ORTHO_FILES = [
    "ESP_018854_1755_RED_C_01_ORTHO.JP2",   # Bradbury Landing
    "PSP_010573_1755_RED_C_01_ORTHO.JP2",
    "ESP_023957_1755_RED_C_01_ORTHO.JP2",
    "PSP_009505_1755_RED_C_01_ORTHO.JP2",
    "ESP_040770_1755_RED_C_01_ORTHO.JP2",   # Bagnold dunes
]


def _find(name: str) -> Path | None:
    for d in RAW_DIRS:
        p = d / name
        if p.exists() and p.stat().st_size > 1_000_000:
            return p
    return None


def _hist(src) -> np.ndarray:
    f = max(1, max(src.width, src.height) // 1024)
    thumb = src.read(1, out_shape=(max(1, src.height // f), max(1, src.width // f)))
    h = np.bincount(thumb.ravel(), minlength=256)[:256].astype(np.float64)
    h[0] = 0
    return h


def _cdf(h: np.ndarray) -> np.ndarray:
    return np.cumsum(h) / h.sum() if h.sum() > 0 else np.linspace(0, 1, 256)


def _match_lut(own: np.ndarray, pooled: np.ndarray) -> np.ndarray:
    """Histogram-match one image to the pooled histogram; 0 stays 0, valid → 1…255."""
    levels = np.arange(256, dtype=np.float64)
    lut = np.clip(np.round(np.interp(_cdf(own), _cdf(pooled), levels)), 1, 255).astype(np.uint8)
    lut[0] = 0
    return lut


def _erode(valid: np.ndarray) -> np.ndarray:
    out = valid.copy()
    out[1:, :] &= valid[:-1, :]
    out[:-1, :] &= valid[1:, :]
    out[:, 1:] &= valid[:, :-1]
    out[:, :-1] &= valid[:, 1:]
    return out


def build(window=STUDY_WINDOW, res_m: float = 1.0, out_path: Path | None = None,
          files: list[str] | None = None, update_metadata: bool = True) -> dict | None:
    """Build the mosaic; returns the metadata "ortho" block, or None if no image is found."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject

    out_path = out_path or OUT_DIR / MOSAIC_NAME
    files = files or ORTHO_FILES
    lon_min, lon_max, lat_min, lat_max = window
    lon0 = (lon_min + lon_max) / 2
    k = math.pi / 180 * MARS_R                       # metres per degree (lat_ts = 0)
    left, right = (lon_min - lon0) * k, (lon_max - lon0) * k
    bottom, top = lat_min * k, lat_max * k
    width = round((right - left) / res_m)
    height = round((top - bottom) / res_m)
    transform = from_bounds(left, bottom, right, top, width, height)  # exact window edges
    crs = CRS.from_proj4(f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0={lon0} +x_0=0 +y_0=0 "
                         f"+R={MARS_R} +units=m +no_defs")

    found = [(n, _find(n)) for n in files]
    missing = [n for n, p in found if p is None]
    sources = [(n, p) for n, p in found if p is not None]
    for n in missing:
        print(f"  WARNING: {n} not found in {', '.join(str(d) for d in RAW_DIRS)} — skipped")
    if not sources:
        print("  WARNING: No ortho photos found; mosaic not built.")
        return None

    hists = {}
    for n, p in sources:
        with rasterio.open(p) as src:
            if src.dtypes[0] != "uint8":
                raise ValueError(f"{n}: expected 8-bit pixels, got {src.dtypes[0]}")
            hists[n] = _hist(src)
    pooled = sum(h / h.sum() for h in hists.values() if h.sum() > 0)

    print(f"  Mosaic grid {width}x{height} px at {res_m} m, {len(sources)} images")
    mosaic = np.zeros((height, width), np.uint8)
    used = []
    for n, p in sources:
        t0 = time.time()
        warped = np.zeros((height, width), np.uint8)
        with rasterio.open(p) as src:
            reproject(rasterio.band(src, 1), warped, src_nodata=0, dst_nodata=0,
                      dst_transform=transform, dst_crs=crs, resampling=Resampling.bilinear)
        take = _erode(warped > 0) & (mosaic == 0)
        filled = int(take.sum())
        mosaic[take] = _match_lut(hists[n], pooled)[warped[take]]
        del warped
        print(f"    {n}: +{100 * filled / mosaic.size:.1f}% of window ({time.time() - t0:.0f}s)")
        if filled:
            used.append(n)
    coverage = float((mosaic > 0).mean())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.tif")
    profile = dict(driver="GTiff", width=width, height=height, count=1, dtype="uint8",
                   crs=crs, transform=transform, nodata=0, tiled=True, blockxsize=512,
                   blockysize=512, compress="deflate", predictor=2, zlevel=6, BIGTIFF="IF_SAFER")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(mosaic, 1)
        dst.build_overviews([2, 4, 8, 16, 32, 64], Resampling.average)
        dst.update_tags(SOURCES=",".join(used), CREDIT=CREDIT)
    tmp.replace(out_path)
    size_mb = out_path.stat().st_size / 1e6
    print(f"  OK: {out_path} ({size_mb:.0f} MB), coverage {coverage * 100:.1f}% of the window")

    block = {
        "available": True,
        "mosaic": out_path.name,
        "sources": used,
        "missing": missing,
        "bounds": {"west": lon_min, "east": lon_max, "south": lat_min, "north": lat_max},
        "resolution_m": res_m,
        "coverage_fraction": round(coverage, 4),
        "note": "HiRISE RED orthoimages merged (first source wins in overlaps), histogram-matched "
                "and clipped to the study window.",
        "credit": CREDIT,
    }
    meta_path = out_path.parent / "metadata.json"
    if update_metadata and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["ortho"] = block
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"  OK: metadata.json 'ortho' updated")
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--res", type=float, default=1.0, help="pixel size in metres (default 1)")
    ap.add_argument("--window", type=float, nargs=4, metavar=("LON_MIN", "LON_MAX", "LAT_MIN", "LAT_MAX"),
                    default=STUDY_WINDOW, help="clip window, degrees (planetocentric, east-positive)")
    a = ap.parse_args()
    return 0 if build(tuple(a.window), a.res) else 1


if __name__ == "__main__":
    sys.exit(main())
