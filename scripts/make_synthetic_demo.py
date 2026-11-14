"""Generate COSMIC TRAIL synthetic demo dataset.

⚠️  SYNTHETIC DATA — NOT REAL TERRAIN ⚠️
===========================================
This script creates a mathematically generated terrain that RESEMBLES Gale Crater
but is NOT derived from any NASA instrument. Elevations, slopes, and coverage are
invented to demonstrate the application's routing and visualisation features.

The dataset is clearly labelled "synthetic_demo" in every output file.
It is kept in data/synthetic_demo/ and is NEVER mixed with real NASA data.
The UI shows a prominent warning on every screen where this dataset is active.

Usage (from the project root):
    python scripts/make_synthetic_demo.py

Output (all in data/synthetic_demo/):
    metadata.json       grid parameters, provenance, disclaimer
    analysis.npz        elevation and slope arrays
    elevation.png       false-colour elevation PNG for the UI layer
    slope.png           slope severity PNG
    hillshade.png       hillshade PNG
    thumbnail.png       80x80 overview
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.terrain import horn_slope_deg

# ---------------------------------------------------------------------------
# Grid parameters (chosen to look like a 10 km × 10 km Gale Crater excerpt)
# The projection origin is near Bradbury Landing.
# ---------------------------------------------------------------------------
LAT0 = -4.5895   # planetocentric latitude of origin
LON0 = 137.4417  # longitude of origin, positive east
RADIUS_M = 3_396_190.0
CELL_M = 5.0          # 5 m analysis cells
WIDTH = 2000          # 10 km east-west
HEIGHT = 2000         # 10 km north-south
X_MIN = -(WIDTH * CELL_M / 2)
Y_MAX = HEIGHT * CELL_M / 2

DISCLAIMER = (
    "SYNTHETIC DATA — NOT REAL TERRAIN. "
    "This dataset was generated mathematically for demonstration purposes. "
    "It does NOT represent actual Mars topography, NASA measurements, or any "
    "real geographic feature. Routing results on this dataset have no scientific "
    "or operational significance."
)


def make_elevation(height: int, width: int, cell: float) -> np.ndarray:
    """Create a plausible-looking crater-floor terrain.

    Shape: flat basin rising gently toward the north (simulating the alluvial
    fan / Aeolis Mons foothills), with two ridge features and a few depressions.
    All numbers are invented.
    """
    rng = np.random.default_rng(42)
    y_idx = np.arange(height)[:, None]  # row index → northing (increases upward)
    x_idx = np.arange(width)[None, :]

    # Base elevation (MOLA-like basin floor, ~ -4500 m)
    base = -4500.0

    # Gentle southward tilt (Aeolis Mons is to the south)
    tilt = (height - y_idx) / height * 200.0  # 200 m rise toward south

    # Broad central depression
    cx, cy = width * 0.4, height * 0.5
    dist_centre = np.hypot((x_idx - cx) * cell, (y_idx - cy) * cell)
    depression = -50.0 * np.exp(-(dist_centre / 1500.0) ** 2)

    # Synthetic "ridge" (NE-SW)
    ridge_x = x_idx - width * 0.6
    ridge_y = y_idx - height * 0.4
    ridge_dist = abs(ridge_x * 0.6 + ridge_y * 0.8) * cell
    ridge = 80.0 * np.exp(-(ridge_dist / 300.0) ** 2)

    # Second low ridge (W side)
    ridge2_x = x_idx - width * 0.2
    ridge2_y = y_idx - height * 0.6
    ridge2_dist = abs(ridge2_x * 0.3 + ridge2_y) * cell
    ridge2 = 50.0 * np.exp(-(ridge2_dist / 400.0) ** 2)

    # Smooth random noise
    # Downsample then upsample for large-scale variation
    noise_small = rng.standard_normal((height // 10, width // 10))
    from PIL import Image as _Image
    noise_up = np.array(_Image.fromarray(noise_small.astype(np.float32)).resize(
        (width, height), resample=_Image.BICUBIC))
    # Keep noise amplitude small so slopes are walkable (< 15 deg median).
    # With 5 m cells, 3 m of random variation gives gentle terrain.
    noise = noise_up * 3.0

    elev = base + tilt + depression + ridge + ridge2 + noise

    # Punch two NoData patches to test the UI
    elev[300:360, 400:460] = np.nan   # artifact-like gap
    elev[1200:1250, 1500:1560] = np.nan

    return elev.astype(np.float32)


def make_hillshade(elev: np.ndarray, cell: float,
                   sun_azimuth_deg: float = 315.0,
                   sun_elevation_deg: float = 45.0) -> np.ndarray:
    """Lambertian hillshade (uint8, 0-255)."""
    az = math.radians(sun_azimuth_deg)
    alt = math.radians(sun_elevation_deg)
    lx = math.cos(alt) * math.sin(az)
    ly = math.cos(alt) * math.cos(az)
    lz = math.sin(alt)
    dx = np.full_like(elev, np.nan)
    dy = np.full_like(elev, np.nan)
    for i in range(1, elev.shape[0] - 1):
        for j in range(1, elev.shape[1] - 1):
            pass
    # Vectorised
    with np.errstate(invalid="ignore"):
        dx = (np.roll(elev, -1, axis=1) - np.roll(elev, 1, axis=1)) / (2 * cell)
        dy = (np.roll(elev, -1, axis=0) - np.roll(elev, 1, axis=0)) / (2 * cell)
    mag = np.sqrt(dx ** 2 + dy ** 2 + 1.0)
    nx, ny, nz = -dx / mag, -dy / mag, 1.0 / mag
    shade = lx * nx + ly * ny + lz * nz
    shade = np.clip(shade, 0.0, 1.0)
    return (shade * 255).astype(np.uint8)


def save_png(arr_uint8: np.ndarray, path: Path) -> str:
    from PIL import Image
    img = Image.fromarray(arr_uint8)
    img.save(str(path))
    return sha256(path)


def false_colour_elevation(elev: np.ndarray) -> np.ndarray:
    """RGB uint8 — viridis-ish palette over the valid range."""
    valid = elev[np.isfinite(elev)]
    lo, hi = float(valid.min()), float(valid.max())
    t = np.clip((elev - lo) / max(hi - lo, 1.0), 0.0, 1.0)
    t = np.where(np.isfinite(elev), t, 0.0)
    r = (68 + (253 - 68) * t).astype(np.uint8)
    g = (1 + (231 - 1) * t ** 0.5).astype(np.uint8)
    b = (84 + (37 - 84) * t ** 2).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def slope_colour(slope: np.ndarray) -> np.ndarray:
    """RGB uint8 — green-yellow-red slope severity."""
    t = np.clip(np.where(np.isfinite(slope), slope / 30.0, 0.0), 0.0, 1.0)
    r = (t * 220).astype(np.uint8)
    g = ((1 - t) * 200).astype(np.uint8)
    b = np.zeros_like(r)
    return np.stack([r, g, b], axis=-1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def sha256_arr(arr: np.ndarray) -> str:
    return hashlib.sha256(arr.tobytes()).hexdigest()


def main():
    from PIL import Image

    out = ROOT / "data" / "synthetic_demo"
    out.mkdir(parents=True, exist_ok=True)

    print("Generating synthetic terrain …")
    elev = make_elevation(HEIGHT, WIDTH, CELL_M)
    slope = horn_slope_deg(elev, CELL_M)

    npz_path = out / "analysis.npz"
    np.savez_compressed(str(npz_path), elevation=elev, slope_deg=slope)
    npz_sha = sha256(npz_path)

    # PNGs (downsample to 1000×1000 for the UI)
    H2, W2 = 1000, 1000

    def down(a, fill=0.0):
        finite = np.where(np.isfinite(a), a, fill)
        from PIL import Image
        return np.array(Image.fromarray(finite.astype(np.float32)).resize(
            (W2, H2), resample=Image.BILINEAR))

    elev_d = down(elev, fill=float(np.nanmin(elev)))
    slope_d = down(slope, fill=0.0)

    elev_path = out / "elevation.png"
    Image.fromarray(false_colour_elevation(elev_d)).save(str(elev_path))

    slope_path = out / "slope.png"
    Image.fromarray(slope_colour(slope_d)).save(str(slope_path))

    hs = make_hillshade(elev_d, CELL_M * (HEIGHT / H2))
    hs_path = out / "hillshade.png"
    Image.fromarray(hs).save(str(hs_path))

    # Thumbnail
    thumb_path = out / "thumbnail.png"
    Image.fromarray(false_colour_elevation(elev_d)).resize((80, 80)).save(str(thumb_path))

    # metadata.json
    valid = np.isfinite(elev) & np.isfinite(slope)
    meta = {
        "schema_version": 1,
        "kind": "synthetic_demo",
        "dataset_id": "synthetic_demo_v1",
        "DISCLAIMER": DISCLAIMER,
        "analysis": {
            "x_min": X_MIN,
            "y_max": Y_MAX,
            "cell_size_m": CELL_M,
            "width": WIDTH,
            "height": HEIGHT,
            "available": True,
            "file": "analysis.npz",
        },
        "crs": {
            "type": "local_eqc",
            "lat0": LAT0,
            "lon0": LON0,
            "radius": RADIUS_M,
            "note": "Projection centred on Bradbury Landing coordinates. SYNTHETIC DATA.",
        },
        "stats": {
            "cells_total": int(elev.size),
            "cells_valid": int(valid.sum()),
            "coverage_fraction": round(float(valid.mean()), 4),
            "elevation_min_m": round(float(np.nanmin(elev)), 2),
            "elevation_max_m": round(float(np.nanmax(elev)), 2),
            "slope_p95_deg": round(float(np.nanpercentile(slope[valid], 95)), 2),
        },
        "checksums": {
            "analysis_npz_sha256": npz_sha,
            "elevation_arr_sha256": sha256_arr(elev),
            "checksum_note": (
                "SHA-256 of the generated files. Because the data are synthetic "
                "(procedurally generated from a fixed seed), these checksums verify "
                "that the files are intact but do NOT prove any NASA provenance."
            ),
        },
        "layers": {
            "elevation_png": {"file": "elevation.png", "sha256": sha256(elev_path),
                               "note": "False-colour elevation. SYNTHETIC."},
            "slope_png": {"file": "slope.png", "sha256": sha256(slope_path),
                          "note": "Slope severity. SYNTHETIC."},
            "hillshade_png": {"file": "hillshade.png", "sha256": sha256(hs_path),
                              "note": "Hillshade. SYNTHETIC."},
        },
        "provenance": {
            "generated_by": "COSMIC TRAIL scripts/make_synthetic_demo.py",
            "seed": 42,
            "note": (
                "All terrain values are mathematically generated and have NO relationship "
                "to any real Mars surface measurements."
            ),
        },
    }
    meta_path = out / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"✓ metadata.json  ({meta_path})")
    print(f"✓ analysis.npz   sha256={npz_sha[:16]}…")
    print(f"✓ elevation.png  slope.png  hillshade.png  thumbnail.png")
    print()
    print("⚠️  SYNTHETIC DATA — this dataset is for demonstration only.")
    print("   Run scripts/prepare_data.py to work with real NASA data.")


if __name__ == "__main__":
    main()
