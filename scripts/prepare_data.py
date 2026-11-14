"""Download and prepare real NASA terrain data for COSMIC TRAIL.

⚠️  REAL DATA REQUIRED — read these notes before running ⚠️
==============================================================
This script downloads publicly available NASA/USGS datasets for a small window
of Gale Crater (the MSL Curiosity rover landing area). The downloads are large:

  HiRISE DTM   DTEEC_024234_1755_024300_1755_U01.IMG     ~444 MB  (tile 1)
  HiRISE DTM   DTEEC_009505_1755_009571_1755_U01.IMG     ~833 MB  (tile 2, optional)
  HiRISE DTM   DTEEC_001488_1750_001752_1750_U02.IMG     ~343 MB  (tile 3, optional)
  HiRISE ortho ESP_024234_1755_RED_C_01_ORTHO.JP2         ~27 MB
  HiRISE ortho 5 RED_C orthos over the study area         ~178 MB (photo layer; merged and
               clipped to data/hirise_gale/ortho_mosaic.tif, ~145 MB, by build_ortho_mosaic.py)
  MOLA global  Mars_MGS_MOLA_DEM_mosaic_global_463m.tif   ~2 GB  (clipped)

Multiple HiRISE tiles are merged using a priority-blend approach: where tiles
overlap the tile with more valid data takes precedence. This can increase
terrain coverage from ~70% to ~90%+.

Data sources and provenance
---------------------------
  HiRISE DTM: https://www.uahirise.org/dtm/ESP_024234_1755
    Product: DTEEC_024234_1755_024300_1755_U01
    Centre: -4.64°, 137.2°E; post spacing ~1.01 m
    Credit: NASA/JPL-Caltech/UArizona
    Tied to MOLA.  Valid elevations: -4623.42 to -4226.53 m (reported)
    Known artifacts: data boxes, CCD seams, faceted areas — documented in
    README at https://www.uahirise.org/PDS/EXTRAS/DTM/ESP/ORB_024200_024299/
       ESP_024234_1755_ESP_024300_1755/README.TXT
    Terms: https://uahirise.org/media/usage.php — public domain; credit required

  MOLA 463 m mosaic:
    https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m
    File: Mars_MGS_MOLA_DEM_mosaic_global_463m.tif (CC0)
    Reference: Smith et al. 2001; Neumann et al. 2001

LIMITATION
----------
Data hosts may be blocked from automated download in some environments.
If the download step fails, the script saves a stub metadata.json that
enables the app's "real data blocked" mode and prints the manual download
instructions you can follow on Windows.

Requires:
    rasterio, numpy, pyproj  (installed in the project venv)

Usage:
    python scripts/prepare_data.py [--study-window LONMIN LONMAX LATMIN LATMAX]
    Default window: 137.35 137.55 -4.75 -4.45  (12 km × 10 km Gale area)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import NamedTuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.geo import MARS_SPHERE_RADIUS_M, LocalEqc, proj_string
from app.terrain import horn_slope_deg

# ---------------------------------------------------------------------------
# Study area default (Gale Crater, Bradbury Landing region)
# ---------------------------------------------------------------------------
DEFAULT_LONMIN, DEFAULT_LONMAX = 137.35, 137.55
DEFAULT_LATMIN, DEFAULT_LATMAX = -4.75, -4.45

# USGS MSL Gale Merged DEM 1m v3 — primary source for filling HiRISE NoData gaps.
# ~3.6 GB; NOT downloaded automatically. Place it at this path manually.
USGS_GALE_DEM = "data/hirise_gale/raw/MSL_Gale_DEM_Mosaic_1m_v3.tif"
USGS_GALE_DEM_URL = "https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif"
USGS_GALE_DEM_INFO = {
    "source": "USGS MSL Gale Merged DEM 1m v3",
    "url": "https://astrogeology.usgs.gov/search/map/mars_msl_gale_merged_dem_1m",
    "download_url": USGS_GALE_DEM_URL,
    "credit": "USGS Astrogeology Science Center",
    "resolution_m": 1,
    "components": ["HiRISE", "CTX", "HRSC"],
    "tied_to": "MOLA",
}

# Analysis grid parameters
ANALYSIS_CELL_M = 5.0   # target cell size after reprojection

# Output folder
OUT_REAL = ROOT / "data" / "hirise_gale"

# ---------------------------------------------------------------------------
# NASA/USGS product information (all verified from published sources)
# ---------------------------------------------------------------------------
HIRISE_DTM_URL = (
    "https://www.uahirise.org/PDS/DTM/ESP/ORB_024200_024299/"
    "ESP_024234_1755_ESP_024300_1755/"
    "DTEEC_024234_1755_024300_1755_U01.IMG"
)
HIRISE_ORTHO_URL = (
    "https://www.uahirise.org/PDS/DTM/ESP/ORB_024200_024299/"
    "ESP_024234_1755_ESP_024300_1755/"
    "ESP_024234_1755_RED_C_01_ORTHO.JP2"
)
MOLA_URL = (
    "https://planetarymaps.usgs.gov/mosaic/"
    "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"
)
HIRISE_README_URL = (
    "https://www.uahirise.org/PDS/EXTRAS/DTM/ESP/ORB_024200_024299/"
    "ESP_024234_1755_ESP_024300_1755/README.TXT"
)

PRODUCTS = {
    "hirise_dtm": {
        "url": HIRISE_DTM_URL,
        "filename": "DTEEC_024234_1755_024300_1755_U01.IMG",
        "size_mb_approx": 444,
        "credit": "NASA/JPL-Caltech/UArizona",
        "terms": "https://uahirise.org/media/usage.php",
        "note": "Public domain; credit required.",
    },
    "hirise_ortho": {
        "url": HIRISE_ORTHO_URL,
        "filename": "ESP_024234_1755_RED_C_01_ORTHO.JP2",
        "size_mb_approx": 27,
        "credit": "NASA/JPL-Caltech/UArizona",
        "terms": "https://uahirise.org/media/usage.php",
    },
    "mola_global": {
        "url": MOLA_URL,
        "filename": "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif",
        "size_mb_approx": 2000,
        "credit": "NASA GSFC MOLA Science Team / USGS",
        "terms": "CC0",
        "note": "Only a small window (< 1 MB) is read using HTTP range request.",
    },
}

# Additional HiRISE tiles that can be manually placed in data/hirise_gale/raw/
# to increase coverage. These are automatically detected and merged.
#
# Tiles below the first three were found in the official HiRISE PDS cumulative DTM
# index (https://www.uahirise.org/PDS/INDEX/DTMCUMINDEX.TAB, searched 2026-11-12) for
# the wider Gale window lon 137.1–137.8°E, lat 5.2–4.0°S. Download each from
#   https://www.uahirise.org/PDS/DTM/<path below>/<file>
# into data/hirise_gale/raw/ and re-run this script. Missing files are skipped.
# Only tiles with valid cells inside STUDY_WINDOW are merged; the rest are listed
# in metadata.json "tiles_skipped". Footprints are the index bounding boxes (°E / °S).
# See SCIENTIFIC_LIMITATIONS.md "HiRISE DTM coverage" for the uncovered areas.
ADDITIONAL_DTM_FILES = [
    "DTEEC_023957_1755_024023_1755_U01.IMG",   # center tile — fills gap between tile1 and tile2
    "DTEEC_009505_1755_009571_1755_U01.IMG",   # right side tile
    "DTEEC_001488_1750_001752_1750_U02.IMG",   # south tile (outside study area, will be skipped)
    # --- inside the current STUDY_WINDOW (would replace USGS gap fill west of 137.43°E) ---
    "DTEEC_018854_1755_018920_1755_U01.IMG",   # 137.336–137.457 / 4.458–4.715 · 426 MB · ESP/ORB_018800_018899/ESP_018854_1755_ESP_018920_1755 · covers Bradbury Landing
    "DTEEC_010573_1755_010639_1755_U01.IMG",   # 137.345–137.467 / 4.355–4.634 · 471 MB · PSP/ORB_010500_010599/PSP_010573_1755_PSP_010639_1755 · covers Bradbury Landing
    "DTEEC_040770_1755_039280_1755_U01.IMG",   # 137.335–137.443 / 4.583–4.792 · 308 MB · ESP/ORB_040700_040799/ESP_040770_1755_ESP_039280_1755 · dunes + rover (A01 version of the same pair also exists)
    "DTEEC_009149_1750_009294_1750_U01.IMG",   # 137.353–137.469 / 4.676–4.923 · 391 MB · PSP/ORB_009100_009199/PSP_009149_1750_PSP_009294_1750 · filled channel / fan
    "DTEEC_009650_1755_009716_1755_U01.IMG",   # 137.235–137.378 / 4.402–4.825 · 833 MB · PSP/ORB_009600_009699/PSP_009650_1755_PSP_009716_1755 · overlaps window's west edge
    "DTEEC_019698_1750_019988_1750_U01.IMG",   # 137.312–137.439 / 4.729–5.041 · 543 MB · ESP/ORB_019600_019699/ESP_019698_1750_ESP_019988_1750 · NW mound; touches window's south edge
    "DTEEC_011417_1755_011562_1755_U01.IMG",   # 137.544–137.678 / 4.256–4.627 · 679 MB · ESP/ORB_011400_011499/ESP_011417_1755_ESP_011562_1755 · only ~6 m strip inside window
    # --- outside the current STUDY_WINDOW (skipped unless the window is widened) ---
    "DTEED_062963_1760_062172_1760_A01.IMG",   # 137.241–137.357 / 3.878–4.197 · 128 MB · 2 m posts · ESP/ORB_062900_062999/ESP_062963_1760_ESP_062172_1760 · Peace Vallis
    "DTEEC_018788_1755_018287_1755_A01.IMG",   # 137.751–137.873 / 4.423–4.743 · 535 MB · ESP/ORB_018700_018799/ESP_018788_1755_ESP_018287_1755
    "DTEEC_012551_1750_012841_1750_U01.IMG",   # 137.159–137.285 / 4.699–5.003 · 525 MB · ESP/ORB_012500_012599/ESP_012551_1750_ESP_012841_1750 · sulfate/clay strata
    "DTEEC_006855_1750_007501_1750_A01.IMG",   # 137.172–137.290 / 4.950–5.222 · 438 MB · PSP/ORB_006800_006899/PSP_006855_1750_PSP_007501_1750 · mound canyon
    "DTEEC_012340_1750_012195_1750_A01.IMG",   # 137.291–137.415 / 5.010–5.369 · 610 MB · ESP/ORB_012300_012399/ESP_012340_1750_ESP_012195_1750 · "grand canyon"
    "DTEEC_008147_1750_007356_1750_H01.IMG",   # 137.381–137.507 / 5.016–5.377 · 621 MB · PSP/ORB_008100_008199/PSP_008147_1750_PSP_007356_1750 · large dunes
]

# HiRISE RED orthoimages (~1 m) for the globe's photo layer, matching the DTM pairs that
# cover the study window. Each sits next to its DTM on the HiRISE PDS. Merged (in this
# priority order: the first file wins where images overlap) and clipped to the study window
# by scripts/build_ortho_mosaic.py. The ESP_024234 ortho (PRODUCTS["hirise_ortho"]) lies
# west of the window and is not part of the mosaic.
# Orbits before ~011000 are the PSP mission phase, hence the PSP_ prefix and folder.
HIRISE_DTM_BASE_URL = "https://www.uahirise.org/PDS/DTM/"
ADDITIONAL_ORTHO_FILES = [
    # (filename, PDS folder, size MB)
    ("ESP_018854_1755_RED_C_01_ORTHO.JP2", "ESP/ORB_018800_018899/ESP_018854_1755_ESP_018920_1755", 35),  # Bradbury Landing
    ("PSP_010573_1755_RED_C_01_ORTHO.JP2", "PSP/ORB_010500_010599/PSP_010573_1755_PSP_010639_1755", 35),
    ("ESP_023957_1755_RED_C_01_ORTHO.JP2", "ESP/ORB_023900_023999/ESP_023957_1755_ESP_024023_1755", 30),
    ("PSP_009505_1755_RED_C_01_ORTHO.JP2", "PSP/ORB_009500_009599/PSP_009505_1755_PSP_009571_1755", 53),
    ("ESP_040770_1755_RED_C_01_ORTHO.JP2", "ESP/ORB_040700_040799/ESP_040770_1755_ESP_039280_1755", 25),  # dunes
]

MANUAL_INSTRUCTIONS = """
======================================================================
MANUAL DOWNLOAD INSTRUCTIONS — data host was not reachable from here
======================================================================

1. HiRISE DTM (444 MB):
   https://www.uahirise.org/PDS/DTM/ESP/ORB_024200_024299/
       ESP_024234_1755_ESP_024300_1755/
       DTEEC_024234_1755_024300_1755_U01.IMG
   Save to:  data/raw/DTEEC_024234_1755_024300_1755_U01.IMG

2. HiRISE Ortho (27 MB):
   https://www.uahirise.org/PDS/DTM/ESP/ORB_024200_024299/
       ESP_024234_1755_ESP_024300_1755/
       ESP_024234_1755_RED_C_01_ORTHO.JP2
   Save to:  data/raw/ESP_024234_1755_RED_C_01_ORTHO.JP2

3. Run this script again after placing the files:
   python scripts/prepare_data.py

The MOLA global mosaic (2 GB) is optional — the script reads only a small
window using an HTTP range request. If that also fails, the app falls back
to HiRISE-derived elevation only.

Credit: NASA/JPL-Caltech/UArizona for HiRISE;
        NASA GSFC MOLA Science Team / USGS for MOLA.
======================================================================
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def try_download(url: str, dest: Path, label: str = "") -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "COSMIC-TRAIL-SpaceApps/1.0 (academic, offline planner)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        print(f"  Downloading {label or url} …")
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as resp, \
             open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = 100 * done // total
                    print(f"\r    {done/1e6:.1f} / {total/1e6:.1f} MB ({pct}%)  ", end="", flush=True)
            print(f"\r    Done in {time.time()-t0:.0f}s, {done/1e6:.1f} MB total.    ")
        return True
    except Exception as exc:
        print(f"  ⚠  Download failed ({exc})")
        return False


class StudyWindow(NamedTuple):
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    lat0: float = 0.0
    lon0: float = 0.0

    def with_centre(self):
        lat0 = (self.lat_min + self.lat_max) / 2
        lon0 = (self.lon_min + self.lon_max) / 2
        return self._replace(lat0=lat0, lon0=lon0)


# ---------------------------------------------------------------------------
# Rasterio-based processing
# ---------------------------------------------------------------------------
def clip_to_local_eqc(src_path: Path, win: StudyWindow, cell_m: float,
                      nodata_in=None) -> np.ndarray:
    """Read a source raster, clip to the study window, reproject to local eqc.

    Handles HiRISE PDS3 DTM files which use an equirectangular projection
    with central_meridian matching the stereo pair centre (~137.24°E for
    DTEEC_024234_1755). The file bounds are in metres relative to that centre,
    NOT in lon/lat degrees.

    Returns a float32 2D array with NaN for NoData.
    """
    import rasterio
    import rasterio.warp
    from pyproj import Transformer

    proj = LocalEqc(win.lat0, win.lon0)
    dst_crs_str = proj.proj()
    dst_crs = rasterio.crs.CRS.from_string(dst_crs_str)

    with rasterio.open(src_path) as src:
        src_crs = src.crs

        # --- Detect nodata ---
        nd = nodata_in if nodata_in is not None else src.nodata
        # HiRISE PDS3 nodata is typically -3.4028e+38 (float32 min)
        if nd is None or abs(float(nd)) < 1:
            nd = -3.4028226550889045e+38

        # --- Print source info for debugging ---
        print(f"    Source CRS: {src_crs.to_string()[:80]}")
        print(f"    Source bounds: {src.bounds}")
        print(f"    Source nodata: {nd}")

        # --- The HiRISE DTM uses equirectangular with central_meridian=137.24
        # and Y measured from Mars equator (not from our local window centre).
        # We must reproject the ENTIRE file first, then clip to our study window.
        # Strategy: reproject full source to our local eqc, using warp.transform_bounds
        # to find where the source actually maps to in our CRS. ---

        from pyproj import Transformer

        # Build a pyproj transformer: source CRS → our local eqc
        src_proj4 = src_crs.to_proj4()
        dst_proj4 = dst_crs_str  # local eqc proj4

        try:
            tf = Transformer.from_crs(src_crs.to_wkt(), dst_proj4, always_xy=True)
        except Exception:
            # Fallback: treat source as Mars geographic
            mars_geog = "+proj=longlat +a=3396190 +b=3396190 +no_defs"
            tf = Transformer.from_crs(mars_geog, dst_proj4, always_xy=True)

        # Transform the four corners of the source file
        sb = src.bounds
        corners_x = [sb.left, sb.right, sb.left, sb.right]
        corners_y = [sb.top, sb.top, sb.bottom, sb.bottom]
        cx, cy = tf.transform(corners_x, corners_y)
        cx = [v for v in cx if np.isfinite(v)]
        cy = [v for v in cy if np.isfinite(v)]

        print(f"    Source corners in local eqc: x=[{min(cx):.0f},{max(cx):.0f}] y=[{min(cy):.0f},{max(cy):.0f}]")

        # Our study window in local eqc
        x0_win, y_top_win = proj.forward(win.lon_min, win.lat_max)
        x1_win, y_bot_win = proj.forward(win.lon_max, win.lat_min)

        # Intersect: use overlap of source coverage and study window
        x0 = max(min(cx), x0_win)
        x1 = min(max(cx), x1_win)
        y_bot = max(min(cy), y_bot_win)
        y_top = min(max(cy), y_top_win)

        print(f"    Study window (local eqc): x=[{x0_win:.0f},{x1_win:.0f}] y=[{y_bot_win:.0f},{y_top_win:.0f}]")
        print(f"    Intersection:             x=[{x0:.0f},{x1:.0f}] y=[{y_bot:.0f},{y_top:.0f}]")

        if x0 >= x1 or y_bot >= y_top:
            print("    ⚠ Source file does not overlap study window — using full source extent")
            x0, x1 = min(cx), max(cx)
            y_bot, y_top = min(cy), max(cy)

        width_px = max(1, int(math.ceil((x1 - x0) / cell_m)))
        height_px = max(1, int(math.ceil((y_top - y_bot) / cell_m)))
        print(f"    Destination grid: {width_px}×{height_px} @ {cell_m}m")

        dst_transform = rasterio.transform.from_bounds(
            x0, y_bot, x1, y_top, width_px, height_px)

        out = np.full((height_px, width_px), np.nan, dtype=np.float32)

        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_transform=src.transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=rasterio.warp.Resampling.bilinear,
            src_nodata=nd,
            dst_nodata=np.nan,
        )

        # Mask nodata and physically impossible elevations for Mars Gale Crater
        out = np.where(np.isclose(out, float(nd), rtol=0, atol=1e30), np.nan, out)
        out = np.where(np.isfinite(out) & (out > -6000) & (out < 1000), out, np.nan)

        valid_count = int(np.isfinite(out).sum())
        print(f"    Valid cells after reproject: {valid_count}/{out.size}")
        if valid_count > 0:
            print(f"    Elevation range: {float(np.nanmin(out)):.1f} to {float(np.nanmax(out)):.1f} m")

        # Update x0/y_top for the caller
        x0, y_top = x0, y_top

    return out, (x0, y_top, cell_m, width_px, height_px)


# ---------------------------------------------------------------------------
# PNG layer generation (same logic as synthetic demo)
# ---------------------------------------------------------------------------
def save_fill_overlay(out_dir: Path, fill_mask: np.ndarray, size: tuple[int, int]):
    """Transparent RGBA overlay marking gap-filled (non-HiRISE-tile) cells: blue tint + hatching.

    `size` is (W, H) of the other PNG layers so the overlay lines up with them.
    Removes a stale overlay when nothing was filled.
    """
    from PIL import Image

    (out_dir / "mola_overlay.png").unlink(missing_ok=True)   # pre-USGS file name
    path = out_dir / "fill_overlay.png"
    if not fill_mask.any():
        path.unlink(missing_ok=True)
        return
    W2, H2 = size
    m = np.array(Image.fromarray(fill_mask.astype(np.uint8) * 255).resize(
        (W2, H2), resample=Image.NEAREST)) > 0
    yy, xx = np.mgrid[0:H2, 0:W2]
    hatch = ((xx + yy) % 10) < 2           # 45° lines every 10 px, 2 px wide
    rgba = np.zeros((H2, W2, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 96, 165, 250   # light blue
    rgba[..., 3] = np.where(m, np.where(hatch, 170, 45), 0)
    Image.fromarray(rgba, mode="RGBA").save(str(path))


def save_png_layers(out_dir: Path, elev: np.ndarray, slope: np.ndarray, cell: float,
                    fill_mask: np.ndarray | None = None):
    from PIL import Image

    H, W = elev.shape
    target = min(1000, H, W)
    scale = max(1, max(H, W) // target)
    H2, W2 = H // scale, W // scale

    def _down(a, fill):
        finite = np.where(np.isfinite(a), a, fill)
        return np.array(Image.fromarray(finite.astype(np.float32)).resize(
            (W2, H2), resample=Image.BILINEAR))

    elev_d = _down(elev, float(np.nanmin(elev)) if np.isfinite(elev).any() else 0.0)
    slope_d = _down(slope, 0.0)

    # False-colour elevation (viridis-ish)
    valid = elev_d[np.isfinite(elev_d)]
    lo, hi = (float(valid.min()), float(valid.max())) if valid.size else (0.0, 1.0)
    t = np.clip((elev_d - lo) / max(hi - lo, 1.0), 0.0, 1.0)
    t = np.where(np.isfinite(elev_d), t, 0.0)
    r_ch = (68 + (253 - 68) * t).astype(np.uint8)
    g_ch = (1 + (231 - 1) * t ** 0.5).astype(np.uint8)
    b_ch = (84 + (37 - 84) * t ** 2).astype(np.uint8)
    Image.fromarray(np.stack([r_ch, g_ch, b_ch], axis=-1)).save(str(out_dir / "elevation.png"))

    # Slope severity
    ts = np.clip(np.where(np.isfinite(slope_d), slope_d / 30.0, 0.0), 0.0, 1.0)
    sr = (ts * 220).astype(np.uint8)
    sg = ((1 - ts) * 200).astype(np.uint8)
    sb = np.zeros_like(sr)
    Image.fromarray(np.stack([sr, sg, sb], axis=-1)).save(str(out_dir / "slope.png"))

    # Hillshade
    az, alt = math.radians(315), math.radians(45)
    lx = math.cos(alt) * math.sin(az)
    ly = math.cos(alt) * math.cos(az)
    lz = math.sin(alt)
    dx_hs = (np.roll(elev_d, -1, axis=1) - np.roll(elev_d, 1, axis=1)) / (2 * cell * scale)
    dy_hs = (np.roll(elev_d, -1, axis=0) - np.roll(elev_d, 1, axis=0)) / (2 * cell * scale)
    mag = np.sqrt(dx_hs ** 2 + dy_hs ** 2 + 1.0)
    shade = np.clip(lx * (-dx_hs / mag) + ly * (-dy_hs / mag) + lz / mag, 0, 1)
    Image.fromarray((shade * 255).astype(np.uint8)).save(str(out_dir / "hillshade.png"))

    # Thumbnail
    Image.fromarray(np.stack([r_ch, g_ch, b_ch], axis=-1)).resize((80, 80)).save(str(out_dir / "thumbnail.png"))

    # Gap-fill overlay (same pixel size as the layers above)
    save_fill_overlay(out_dir, fill_mask if fill_mask is not None
                      else np.zeros(elev.shape, dtype=bool), (W2, H2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def write_unavailable_stub(out_dir: Path, reason: str, products_tried: list):
    out_dir.mkdir(parents=True, exist_ok=True)
    lat0 = (DEFAULT_LATMIN + DEFAULT_LATMAX) / 2
    lon0 = (DEFAULT_LONMIN + DEFAULT_LONMAX) / 2
    meta = {
        "schema_version": 1,
        "kind": "real_unavailable",
        "dataset_id": "hirise_gale_unavailable",
        "unavailable_reason": reason,
        "manual_download": MANUAL_INSTRUCTIONS,
        "analysis": {
            "x_min": 0, "y_max": 0, "cell_size_m": ANALYSIS_CELL_M,
            "width": 1, "height": 1,
            "available": False, "file": "analysis.npz",
        },
        "crs": {"type": "local_eqc", "lat0": lat0, "lon0": lon0, "radius": MARS_SPHERE_RADIUS_M},
        "products_attempted": products_tried,
        "provenance": {
            "note": "Real data was not downloaded. See manual_download for instructions.",
            "sources": PRODUCTS,
        },
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("  Wrote unavailable stub to", out_dir / "metadata.json")


def process_hirise_dtm(raw_path: Path, win: StudyWindow) -> tuple:
    print("  Processing HiRISE DTM …")
    elev, geom = clip_to_local_eqc(raw_path, win, ANALYSIS_CELL_M, nodata_in=None)
    return elev, geom


def window_bounds_local(win: StudyWindow) -> tuple[float, float, float, float]:
    """Study window in local eqc metres: (x_min, x_max, y_min, y_max)."""
    proj = LocalEqc(win.lat0, win.lon0)
    x0, y_top = proj.forward(win.lon_min, win.lat_max)
    x1, y_bot = proj.forward(win.lon_max, win.lat_min)
    return x0, x1, y_bot, y_top


def valid_cells_in_window(elev: np.ndarray, geom: tuple, win_bounds: tuple) -> int:
    """Count finite cells whose centres fall inside the study window."""
    x_min, y_max, cell_m, w, h = geom
    wx0, wx1, wy0, wy1 = win_bounds
    xs = x_min + (np.arange(w) + 0.5) * cell_m
    ys = y_max - (np.arange(h) + 0.5) * cell_m
    cols = (xs >= wx0) & (xs <= wx1)
    rows = (ys >= wy0) & (ys <= wy1)
    if not cols.any() or not rows.any():
        return 0
    return int(np.isfinite(elev[np.ix_(rows, cols)]).sum())


def hirise_tile_info(path: Path, elev: np.ndarray) -> dict:
    """Describe a HiRISE DTM tile from its filename, file header and processed data.

    Product ID format: DTEEC_<orbit1>_<lat>_<orbit2>_<lat>_<version>.
    Observations before orbit 11000 belong to the Primary Science Phase (PSP_),
    later ones to the Extended Science Phase (ESP_).
    """
    import rasterio
    from pyproj import Transformer

    stem = path.stem
    parts = stem.split("_")
    pair = []
    if len(parts) >= 5:
        for orbit, lat in ((parts[1], parts[2]), (parts[3], parts[4])):
            phase = "PSP" if int(orbit) < 11000 else "ESP"
            pair.append(f"{phase}_{orbit}_{lat}")

    info = {
        "product_id": stem,
        "file": path.name,
        "stereo_pair": pair,
        "credit": "NASA/JPL-Caltech/UArizona",
        "terms": "https://uahirise.org/media/usage.php",
        "known_artifacts": ["data boxes", "CCD seams", "faceted areas"],
        "source_page": f"https://www.uahirise.org/dtm/{pair[0]}" if pair else None,
    }
    with rasterio.open(path) as src:
        info["post_spacing_m"] = round(float(abs(src.res[0])), 2)
        b = src.bounds
        tf = Transformer.from_crs(src.crs.to_wkt(),
                                  "+proj=longlat +a=3396190 +b=3396190 +no_defs",
                                  always_xy=True)
        lon, lat = tf.transform((b.left + b.right) / 2, (b.top + b.bottom) / 2)
        info["centre_lat_deg"] = round(float(lat), 3)
        info["centre_lon_deg"] = round(float(lon), 3)
    if np.isfinite(elev).any():
        info["valid_elevation_range_m"] = [round(float(np.nanmin(elev)), 2),
                                           round(float(np.nanmax(elev)), 2)]
    if path.name == PRODUCTS["hirise_dtm"]["filename"]:
        info["source_url"] = HIRISE_DTM_URL
    return info


# Geographic box (lon/lat, Mars sphere) that gap-fill sources are cropped to.
# It must contain the whole analysis grid; cells outside it stay NoData.
FILL_BOX = {"lon_min": 137.3, "lon_max": 137.6, "lat_min": -4.8, "lat_max": -4.4}


def harmonic_fill(values: np.ndarray, known: np.ndarray, iters: int = 40) -> np.ndarray:
    """Smoothly interpolate `values` into cells where `known` is False.

    Solves Laplace's equation (each unknown cell = mean of its 4 neighbours)
    with known cells held fixed, coarse-to-fine: the grid is halved until tiny,
    solved there, then upsampled and relaxed with Jacobi iterations at each
    finer level. The result matches the known values exactly at gap edges and
    varies smoothly (no steps) across the gap — distance-weighted by construction.
    """
    v = np.where(known, values, 0.0).astype(np.float64)
    h, w = v.shape
    if known.all() or not known.any():
        return np.where(known, v, 0.0)
    if min(h, w) <= 8:
        init = np.full((h, w), v[known].mean())
    else:
        # Pull: 2×2 block average of known cells (pad to even size).
        ph, pw = h + h % 2, w + w % 2
        vp = np.zeros((ph, pw)); kp = np.zeros((ph, pw))
        vp[:h, :w] = v; kp[:h, :w] = known
        s = vp.reshape(ph // 2, 2, pw // 2, 2).sum(axis=(1, 3))
        n = kp.reshape(ph // 2, 2, pw // 2, 2).sum(axis=(1, 3))
        coarse = harmonic_fill(np.divide(s, n, out=np.zeros_like(s), where=n > 0), n > 0, iters)
        # Push: nearest upsample as the starting guess for this level.
        init = np.repeat(np.repeat(coarse, 2, axis=0), 2, axis=1)[:h, :w]
    x = np.where(known, v, init)
    for _ in range(iters):
        p = np.pad(x, 1, mode="edge")
        avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) * 0.25
        x = np.where(known, v, avg)
    return x


def _source_on_grid(src_path: Path, geom: tuple, win: StudyWindow) -> np.ndarray:
    """Warp a DEM onto the local-eqc analysis grid (bilinear), cropped to FILL_BOX.

    GDAL's warper reads only the source rows/columns that the destination grid
    needs, so multi-GB mosaics are never loaded whole. Works for any source CRS
    rasterio can read (MOLA global eqc, USGS Gale mosaic eqc, ...).
    """
    import rasterio
    import rasterio.warp
    from rasterio.transform import from_origin

    x_min, y_max, cell_m, w, h = geom
    proj = LocalEqc(win.lat0, win.lon0)
    dst_crs = rasterio.crs.CRS.from_string(proj.proj())
    out = np.full((h, w), np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        nd = src.nodata
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=from_origin(x_min, y_max, cell_m, cell_m),
            dst_crs=dst_crs,
            resampling=rasterio.warp.Resampling.bilinear,
            src_nodata=nd,
            dst_nodata=np.nan,
        )
        scale = (src.scales or (1.0,))[0] or 1.0
        offset = (src.offsets or (0.0,))[0] or 0.0
    if nd is not None:
        out[np.isclose(out, nd)] = np.nan
    out = out * scale + offset
    out[~((out > -9000) & (out < 22000))] = np.nan   # physically impossible on Mars

    # Crop to FILL_BOX: local eqc is linear in lon/lat, so the box is a rectangle.
    bx0, by1 = proj.forward(FILL_BOX["lon_min"], FILL_BOX["lat_max"])
    bx1, by0 = proj.forward(FILL_BOX["lon_max"], FILL_BOX["lat_min"])
    xs = x_min + (np.arange(w) + 0.5) * cell_m
    ys = y_max - (np.arange(h) + 0.5) * cell_m
    out[:, (xs < bx0) | (xs > bx1)] = np.nan
    out[(ys < by0) | (ys > by1), :] = np.nan
    return out


def _fill_gaps(elev: np.ndarray, fill: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Fill NaN cells of `elev` from `fill`, with edge blending. Never overwrites HiRISE.

    Edge blending: the HiRISE - source offset measured on HiRISE cells is spread
    smoothly into each gap (harmonic_fill) and added to the source, so the two
    surfaces meet without a step at the gap boundary.
    """
    gaps = ~np.isfinite(elev)
    info: dict = {"cells_nodata_before": int(gaps.sum())}
    both = np.isfinite(elev) & np.isfinite(fill)
    if both.any():
        diff = elev[both] - fill[both]
        info["hirise_minus_source_median_m"] = round(float(np.median(diff)), 2)
        info["hirise_minus_source_p05_p95_m"] = [round(float(np.percentile(diff, 5)), 2),
                                                 round(float(np.percentile(diff, 95)), 2)]
    mask = gaps & np.isfinite(fill)
    filled = elev.copy()
    if both.any() and mask.any():
        corr = harmonic_fill(np.where(both, elev - fill, 0.0), both).astype(np.float32)
        info["edge_blending"] = "harmonic (Laplace) interpolation of HiRISE - source offset"
        info["blend_correction_p05_p95_m"] = [round(float(np.percentile(corr[mask], 5)), 2),
                                              round(float(np.percentile(corr[mask], 95)), 2)]
    else:
        corr = np.zeros_like(fill)
        info["edge_blending"] = "none (no overlap between HiRISE and source)"
    filled[mask] = fill[mask] + corr[mask]
    info["cells_filled"] = int(mask.sum())
    info["cells_nodata_after"] = int((~np.isfinite(filled)).sum())
    return filled, mask, info


def fill_nodata_from_usgs_dem(elev: np.ndarray, geom: tuple, win: StudyWindow,
                              path: Path | None = None):
    """Fill HiRISE NoData cells from the USGS MSL Gale Merged DEM 1m v3.

    Returns (filled_elev, usgs_filled_mask, info), or None when the file is
    missing so the caller can fall back to MOLA.
    """
    path = Path(path) if path else ROOT / USGS_GALE_DEM
    if not path.exists():
        print(f"  USGS DEM not found at {path}. Download it from: {USGS_GALE_DEM_URL}")
        return None
    print(f"  Filling NoData gaps from USGS Gale DEM: {path.name}")
    return _fill_gaps(elev, _source_on_grid(path, geom, win))


def fill_nodata_from_mola(elev: np.ndarray, geom: tuple, win: StudyWindow,
                          mola_path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """Fallback: fill HiRISE NoData cells from the MOLA 463 m global mosaic."""
    print(f"  Filling NoData gaps from MOLA (fallback): {mola_path.name}")
    return _fill_gaps(elev, _source_on_grid(mola_path, geom, win))


def merge_tiles(tiles: list[tuple]) -> tuple:
    """Merge multiple (elev_array, geom) tiles into a single grid.

    geom = (x_min, y_max, cell_m, width, height)
    Strategy: compute bounding box of tiles that actually have valid data,
    create output grid, fill with each tile (later tiles fill gaps).
    Tiles with no valid data are skipped.
    """
    if len(tiles) == 1:
        return tiles[0]

    # Filter tiles that actually have valid data
    valid_tiles = []
    for elev, geom in tiles:
        if np.isfinite(elev).sum() > 0:
            valid_tiles.append((elev, geom))
        else:
            print(f"  Skipping tile with 0 valid cells")

    if len(valid_tiles) == 1:
        print("  Only 1 tile has valid data — no merge needed")
        return valid_tiles[0]

    cell_m = valid_tiles[0][1][2]  # all tiles same cell size

    # Find bounding box of ACTUAL valid data pixels (not full tile extents)
    # This avoids huge empty grids when tiles don't overlap well
    all_data_x_min, all_data_x_max = [], []
    all_data_y_min, all_data_y_max_vals = [], []

    for elev, (x_min, y_max, cm, w, h) in valid_tiles:
        rows_valid, cols_valid = np.where(np.isfinite(elev))
        if len(rows_valid) == 0:
            continue
        col0, col1 = int(cols_valid.min()), int(cols_valid.max())
        row0, row1 = int(rows_valid.min()), int(rows_valid.max())
        # Convert pixel indices back to coordinates
        data_x_min = x_min + col0 * cm
        data_x_max = x_min + (col1 + 1) * cm
        data_y_max = y_max - row0 * cm
        data_y_min = y_max - (row1 + 1) * cm
        all_data_x_min.append(data_x_min)
        all_data_x_max.append(data_x_max)
        all_data_y_min.append(data_y_min)
        all_data_y_max_vals.append(data_y_max)

    out_x_min = min(all_data_x_min)
    out_x_max = max(all_data_x_max)
    out_y_max = max(all_data_y_max_vals)
    out_y_min = min(all_data_y_min)

    out_w = max(1, int(math.ceil((out_x_max - out_x_min) / cell_m)))
    out_h = max(1, int(math.ceil((out_y_max - out_y_min) / cell_m)))

    print(f"  Merged grid: {out_w}×{out_h} cells ({out_x_min:.0f}…{out_x_max:.0f} x {out_y_min:.0f}…{out_y_max:.0f})")

    merged = np.full((out_h, out_w), np.nan, dtype=np.float32)

    for i, (elev, (x_min, y_max, cm, w, h)) in enumerate(valid_tiles):
        # Compute pixel offset of this tile in the merged grid
        col_off = int(round((x_min - out_x_min) / cell_m))
        row_off = int(round((out_y_max - y_max) / cell_m))

        # Clip to output bounds
        src_row0 = max(0, -row_off)
        src_col0 = max(0, -col_off)
        dst_row0 = max(0, row_off)
        dst_col0 = max(0, col_off)
        rows = min(h - src_row0, out_h - dst_row0)
        cols = min(w - src_col0, out_w - dst_col0)

        if rows <= 0 or cols <= 0:
            print(f"  Tile {i+1}: no overlap with merged grid, skipping")
            continue

        src_slice = elev[src_row0:src_row0+rows, src_col0:src_col0+cols]
        dst_slice = merged[dst_row0:dst_row0+rows, dst_col0:dst_col0+cols]

        # Fill gaps: where merged is NaN, use this tile's data
        gap_mask = ~np.isfinite(dst_slice) & np.isfinite(src_slice)
        dst_slice[gap_mask] = src_slice[gap_mask]
        merged[dst_row0:dst_row0+rows, dst_col0:dst_col0+cols] = dst_slice

        filled = int(gap_mask.sum())
        print(f"  Tile {i+1}: filled {filled:,} new cells")

    return merged, (out_x_min, out_y_max, cell_m, out_w, out_h)


def main():
    parser = argparse.ArgumentParser(description="Prepare real NASA terrain for COSMIC TRAIL")
    parser.add_argument("--study-window", nargs=4, type=float,
                        metavar=("LONMIN", "LONMAX", "LATMIN", "LATMAX"),
                        default=[DEFAULT_LONMIN, DEFAULT_LONMAX, DEFAULT_LATMIN, DEFAULT_LATMAX])
    parser.add_argument("--skip-download", action="store_true",
                        help="Use files already in data/raw/ without re-downloading")
    args = parser.parse_args()

    lonmin, lonmax, latmin, latmax = args.study_window
    win = StudyWindow(lonmin, lonmax, latmin, latmax).with_centre()

    # Check multiple possible locations for manually placed files
    raw_dir = ROOT / "data" / "raw"
    alt_raw_dir = ROOT / "data" / "hirise_gale" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    OUT_REAL.mkdir(parents=True, exist_ok=True)

    def find_file(filename):
        """Find a file in raw/, hirise_gale/raw/, or hirise_gale/ — whichever exists first."""
        for d in [raw_dir, alt_raw_dir, OUT_REAL]:
            p = d / filename
            if p.exists() and p.stat().st_size > 1_000_000:  # at least 1 MB
                return p
        return None

    products_tried = []

    # --- Try to get HiRISE DTM ---
    dtm_filename = PRODUCTS["hirise_dtm"]["filename"]
    dtm_local = find_file(dtm_filename)
    have_dtm = dtm_local is not None

    if have_dtm:
        size_mb = dtm_local.stat().st_size / 1e6
        print(f"\n[1/3] Found HiRISE DTM locally: {dtm_local} ({size_mb:.1f} MB)")
        if size_mb < 400:
            print(f"  ⚠  File is only {size_mb:.1f} MB — expected ~444 MB. May be incomplete.")
            print("  Trying to re-download a fresh copy …")
            dest = raw_dir / dtm_filename
            have_dtm = try_download(PRODUCTS["hirise_dtm"]["url"], dest, dtm_filename)
            if have_dtm:
                dtm_local = dest
        products_tried.append({"id": "hirise_dtm", "source": str(dtm_local), "size_mb": round(size_mb, 1)})
    else:
        print("\n[1/3] Downloading HiRISE DTM (~444 MB) …")
        dest = raw_dir / dtm_filename
        have_dtm = try_download(PRODUCTS["hirise_dtm"]["url"], dest, dtm_filename)
        if have_dtm:
            dtm_local = dest
        products_tried.append({"id": "hirise_dtm", "downloaded": have_dtm, "url": PRODUCTS["hirise_dtm"]["url"]})


    # --- Try to get HiRISE ortho ---
    ortho_filename = PRODUCTS["hirise_ortho"]["filename"]
    ortho_local = find_file(ortho_filename)
    have_ortho = ortho_local is not None
    if not have_ortho and not args.skip_download:
        print("\n[2/3] Downloading HiRISE ortho (~27 MB) …")
        dest = raw_dir / ortho_filename
        have_ortho = try_download(PRODUCTS["hirise_ortho"]["url"], dest, ortho_filename)
        if have_ortho:
            ortho_local = dest
    elif have_ortho:
        print(f"\n[2/3] Found HiRISE ortho locally: {ortho_local}")

    # --- Orthoimages over the study window (photo layer only; not used for routing) ---
    # Saved next to the dataset (data/hirise_gale/raw/), then merged + clipped below.
    ortho_files: list[str] = []
    for name, folder, size_mb in ADDITIONAL_ORTHO_FILES:
        p = find_file(name)
        if p is None and not args.skip_download:
            print(f"  Downloading HiRISE ortho {name} (~{size_mb} MB) …")
            alt_raw_dir.mkdir(parents=True, exist_ok=True)
            part = alt_raw_dir / (name + ".part")
            if try_download(f"{HIRISE_DTM_BASE_URL}{folder}/{name}", part, name):
                p = part.replace(alt_raw_dir / name)
            else:
                part.unlink(missing_ok=True)  # never leave a truncated JP2 behind
        if p is not None:
            ortho_files.append(p.name)
        else:
            print(f"  ⚠  Ortho {name} not available — the photo layer will have a gap there.")
    ortho_block = {"available": False, "note": "No HiRISE ortho photos over the study window."}
    if ortho_files:
        print("\n  Building the HiRISE photo mosaic (merge + clip to the study window) …")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_ortho_mosaic import build as build_ortho_mosaic
        try:
            ortho_block = build_ortho_mosaic(
                window=(lonmin, lonmax, latmin, latmax), files=ortho_files,
                out_path=OUT_REAL / "ortho_mosaic.tif", update_metadata=False,
            ) or ortho_block
        except Exception as exc:
            print(f"  ⚠  Ortho mosaic failed ({exc}); the photo layer will be unavailable.")
            ortho_block = {"available": False, "note": f"Ortho mosaic failed: {exc}"}

    # --- Collect every DTM tile available locally ---
    # No tile is hard-coded as primary: the best one is picked below by how
    # many valid cells it has inside the study window.
    candidate_paths = [dtm_local] if have_dtm else []
    for extra_name in ADDITIONAL_DTM_FILES:
        p = find_file(extra_name)
        if p is not None:
            size_mb = p.stat().st_size / 1e6
            print(f"  Found extra tile: {extra_name} ({size_mb:.0f} MB)")
            candidate_paths.append(p)

    if not candidate_paths:
        print("\n⚠  No HiRISE DTM tile available. Creating unavailable stub.")
        print(MANUAL_INSTRUCTIONS)
        write_unavailable_stub(OUT_REAL, "HiRISE DTM download failed or not attempted.", products_tried)
        return 1

    win_bounds = window_bounds_local(win)
    wx0, wx1, wy0, wy1 = win_bounds
    print(f"\n[3/3] Processing terrain ({len(candidate_paths)} candidate tile"
          f"{'s' if len(candidate_paths) > 1 else ''}) …")
    print(f"  Study window (local eqc): x=[{wx0:.0f},{wx1:.0f}] y=[{wy0:.0f},{wy1:.0f}]")

    # --- Process each tile; keep only those with valid data inside the window ---
    kept = []        # (path, elev, geom, cells_in_window)
    tiles_skipped = []
    for path in candidate_paths:
        print(f"\n  Tile {path.name}:")
        try:
            t_elev, t_geom = process_hirise_dtm(path, win)
        except Exception as exc:
            print(f"  ⚠  Skipping {path.name}: {exc}")
            tiles_skipped.append({"file": path.name, "reason": f"processing failed: {exc}"})
            continue
        n_in = valid_cells_in_window(t_elev, t_geom, win_bounds)
        if n_in == 0:
            print(f"  ⚠  Skipping {path.name}: no valid data inside the study window")
            tiles_skipped.append({"file": path.name, "reason": "no valid data inside study window"})
            continue
        print(f"  {n_in:,} valid cells inside the study window")
        kept.append((path, t_elev, t_geom, n_in))

    if not kept:
        reason = "No DTM tile has valid data inside the study window."
        print(f"\n⚠  {reason}")
        write_unavailable_stub(OUT_REAL, reason, products_tried)
        return 1

    # Best tile first: merge_tiles() only fills gaps, so earlier tiles win overlaps.
    kept.sort(key=lambda t: t[3], reverse=True)
    best_path, best_elev, best_geom, _ = kept[0]
    print(f"\n  Best tile: {best_path.name}")

    # --- Merge tiles ---
    used = kept
    if len(kept) > 1:
        print(f"\n  Merging {len(kept)} tiles …")
        merged_elev, merged_geom = merge_tiles([(t[1], t[2]) for t in kept])
        merged_cov = int(np.isfinite(merged_elev).sum()) / merged_elev.size
        single_cov = int(np.isfinite(best_elev).sum()) / best_elev.size
        print(f"  Best single tile: {single_cov:.1%}  |  Merged: {merged_cov:.1%}")

        if merged_cov >= single_cov * 0.90:
            print(f"  ✓ Using merged result ({merged_cov:.1%} coverage)")
            elev, (x_min, y_max, cell, width, height) = merged_elev, merged_geom
        else:
            # Tiles too far apart — gap hurts coverage, use best single tile
            print(f"  ✓ Tiles have gap — using best single tile only ({single_cov:.1%} coverage)")
            elev, (x_min, y_max, cell, width, height) = best_elev, best_geom
            used = kept[:1]
            tiles_skipped += [{"file": t[0].name, "reason": "merge would leave a coverage gap"}
                              for t in kept[1:]]
    else:
        elev, (x_min, y_max, cell, width, height) = best_elev, best_geom

    hirise_mask = np.isfinite(elev)

    # --- Fill HiRISE NoData gaps: USGS Gale merged DEM first, MOLA as fallback ---
    grid_geom = (x_min, y_max, cell, width, height)
    usgs_mask = np.zeros_like(hirise_mask)
    mola_mask = np.zeros_like(hirise_mask)
    usgs_path = ROOT / USGS_GALE_DEM
    usgs_info: dict = {**USGS_GALE_DEM_INFO, "available": usgs_path.exists()}
    mola_info: dict | None = None
    fill_source = None
    print()
    try:
        res = fill_nodata_from_usgs_dem(elev, grid_geom, win, usgs_path)
    except Exception as exc:
        print(f"  ⚠  USGS DEM gap fill failed: {exc}")
        usgs_info["error"] = str(exc)
        res = None
    if res is not None:
        elev, usgs_mask, fill_info = res
        usgs_info.update(fill_info)
        fill_source = "usgs"
    else:
        mola_path = find_file(PRODUCTS["mola_global"]["filename"])
        mola_info = {"available": mola_path is not None}
        if mola_path is not None:
            try:
                elev, mola_mask, fill_info = fill_nodata_from_mola(elev, grid_geom, win, mola_path)
                mola_info.update(fill_info)
                fill_source = "mola"
            except Exception as exc:
                print(f"  ⚠  MOLA gap fill failed, keeping NoData: {exc}")
                mola_info["error"] = str(exc)
        else:
            print("  MOLA mosaic not found either — NoData gaps left unfilled.")

    fill_mask = usgs_mask | mola_mask
    if fill_source:
        fi = usgs_info if fill_source == "usgs" else mola_info
        print(f"  NoData cells before: {fi['cells_nodata_before']:,}")
        print(f"  ✓ Filled:            {fi['cells_filled']:,} cells ({fill_source.upper()})")
        print(f"  NoData cells after:  {fi['cells_nodata_after']:,}")
        if "hirise_minus_source_median_m" in fi:
            lo, hi = fi["hirise_minus_source_p05_p95_m"]
            print(f"  HiRISE − source where both exist: median {fi['hirise_minus_source_median_m']} m "
                  f"(5–95%: {lo} to {hi} m)")
        if "blend_correction_p05_p95_m" in fi:
            lo, hi = fi["blend_correction_p05_p95_m"]
            print(f"  Edge blending applied: correction on filled cells {lo} to {hi} m (5–95%)")

    # Slope is computed over HiRISE + fill together, so filled cells get a slope
    # instead of NaN.
    slope = horn_slope_deg(elev, cell)
    valid = np.isfinite(elev) & np.isfinite(slope)
    cov = float(valid.mean())
    print(f"  Grid: {width}×{height} cells at {cell} m; coverage {cov:.1%} "
          f"(HiRISE {hirise_mask.mean():.1%}, USGS fill {usgs_mask.mean():.1%}, "
          f"MOLA fill {mola_mask.mean():.1%})")

    if np.isfinite(elev).any():
        e_min = float(np.nanmin(elev))
        e_max = float(np.nanmax(elev))
        print(f"  Elevation range: {e_min:.1f} to {e_max:.1f} m")
    else:
        print("  ⚠  No valid elevation values in study window — check window coordinates.")

    tile_shas = {t[0].name: sha256_file(t[0]) for t in used}
    tile_infos = [hirise_tile_info(t[0], t[1]) for t in used]
    used_names = [t[0].name for t in used]
    npz_path = OUT_REAL / "analysis.npz"
    # usgs_filled / mola_filled mark cells whose elevation came from that fill
    # source instead of the merged HiRISE DTM tiles.
    np.savez_compressed(str(npz_path), elevation=elev, slope_deg=slope,
                        usgs_filled=usgs_mask, mola_filled=mola_mask)
    npz_sha = sha256_file(npz_path)

    # PNG layers
    print("  Generating PNG layers …")
    save_png_layers(OUT_REAL, elev, slope, cell, fill_mask)

    # metadata.json
    meta = {
        "schema_version": 1,
        "kind": "real_hirise",
        "dataset_id": "+".join(info["product_id"] for info in tile_infos),
        "tiles_merged": used_names,
        "tile_count": len(used_names),
        "tiles_skipped": tiles_skipped,
        "analysis": {
            "x_min": float(x_min), "y_max": float(y_max),
            "cell_size_m": float(cell), "width": int(width), "height": int(height),
            "available": True, "file": "analysis.npz",
        },
        "crs": {
            "type": "local_eqc",
            "lat0": float(win.lat0), "lon0": float(win.lon0),
            "radius": MARS_SPHERE_RADIUS_M,
        },
        "study_window": {
            "lon_min": float(win.lon_min), "lon_max": float(win.lon_max),
            "lat_min": float(win.lat_min), "lat_max": float(win.lat_max),
        },
        "stats": {
            "cells_total": int(elev.size),
            "cells_valid": int(valid.sum()),
            "coverage_fraction": round(cov, 4),
            "elevation_min_m": round(float(np.nanmin(elev)), 2) if np.isfinite(elev).any() else None,
            "elevation_max_m": round(float(np.nanmax(elev)), 2) if np.isfinite(elev).any() else None,
            "slope_p95_deg": round(float(np.nanpercentile(slope[valid], 95)), 2) if valid.any() else None,
            "cells_hirise": int(hirise_mask.sum()),
            "cells_usgs_filled": int(usgs_mask.sum()),
            "cells_mola_filled": int(mola_mask.sum()),
            "hirise_fraction": round(float(hirise_mask.mean()), 4),
            "usgs_filled_fraction": round(float(usgs_mask.mean()), 4),
            "mola_filled_fraction": round(float(mola_mask.mean()), 4),
            "filled_fraction": round(float(fill_mask.mean()), 4),
        },
        # Which source filled the HiRISE gaps: "usgs", "mola" (fallback) or null.
        "fill_source": fill_source,
        "usgs_fill": {
            **usgs_info,
            "read_box_deg": FILL_BOX,
            "resampling": "bilinear, 1 m → 5 m",
            "mask": "analysis.npz key 'usgs_filled' (True = elevation from USGS Gale DEM, not HiRISE tiles)",
        },
        **({"mola_fill": {
            **mola_info,
            "source": PRODUCTS["mola_global"]["filename"],
            "credit": PRODUCTS["mola_global"]["credit"],
            "terms": PRODUCTS["mola_global"]["terms"],
            "read_box_deg": FILL_BOX,
            "resampling": "bilinear, 463 m → 5 m",
            "mask": "analysis.npz key 'mola_filled' (True = elevation from MOLA, not HiRISE)",
        }} if mola_info is not None else {}),
        "checksums": {
            # Primary (best) tile; every merged tile is listed in source_dtm_sha256_by_tile.
            "source_dtm_sha256": tile_shas[used_names[0]],
            "source_dtm_sha256_by_tile": tile_shas,
            "analysis_npz_sha256": npz_sha,
            "checksum_note": (
                "SHA-256 of the source files and the processed output. "
                "These confirm file integrity but do NOT independently verify "
                "that the file was produced by NASA/JPL/UArizona."
            ),
        },
        "provenance": {
            # Tile with the most valid cells inside the study window.
            "primary_source": tile_infos[0],
            "additional_sources": tile_infos[1:],
            "processing": {
                "reprojection": f"local eqc, lat0={win.lat0:.4f}, lon0={win.lon0:.4f}, R=3396190 m",
                "slope_method": "Horn (1981) 3×3 finite difference; border and NoData-adjacent cells → NaN",
                "cell_size_m": ANALYSIS_CELL_M,
                "tool": "rasterio + numpy, COSMIC TRAIL scripts/prepare_data.py",
            },
            "reference": "Smith, D.E. et al. (2001). Mars Orbiter Laser Altimeter: "
                         "Experiment summary after the first year of global mapping of Mars. "
                         "JGR Planets 106(E10).",
            "limitation_note": (
                f"The analysis grid is a window clip and bilinear resampling of {len(used_names)} "
                f"HiRISE DTM tile{'s' if len(used_names) > 1 else ''}"
                f"{' merged (best tile wins where they overlap)' if len(used_names) > 1 else ''}. "
                "Known HiRISE artifacts (data boxes, seams) are retained as NoData or erroneous "
                "values in the source; they appear as NoData clusters in the output. "
                + (f"{usgs_mask.mean():.1%} of cells had no data in the merged HiRISE tiles and "
                   "were filled from the USGS MSL Gale Merged DEM 1m v3 (HiRISE+CTX+HRSC blend), "
                   "edge-blended to the HiRISE tiles. " if usgs_mask.any() else "")
                + (f"{mola_mask.mean():.1%} of cells had no HiRISE data and were filled from the "
                   "MOLA 463 m global DEM (USGS Gale DEM not available); those cells are ~90× "
                   "coarser, so their slopes are smoothed and under-state real local steepness. "
                   if mola_mask.any() else "")
                + "Slope thresholds used for routing are based on Apollo EVA traverses and NASA MSL Engineering User Guide thresholds. "
                "See SCIENTIFIC_LIMITATIONS.md for full caveats."
            ),
        },
        # HiRISE photo layer: data/hirise_gale/ortho_mosaic.tif (scripts/build_ortho_mosaic.py).
        "ortho": ortho_block,
    }
    (OUT_REAL / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\n✓ Done.  Output: {OUT_REAL}/")
    print(f"  analysis.npz sha256={npz_sha[:16]}…")
    print("  Next: python -m uvicorn app.main:app --reload")
    return 0


if __name__ == "__main__":
    sys.exit(main())