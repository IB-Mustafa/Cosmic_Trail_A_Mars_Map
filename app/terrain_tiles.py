"""Height tiles for the 3D globe (Cesium CustomHeightmapTerrainProvider).

Tiling: Cesium GeographicTilingScheme — level z has 2·2^z × 2^z tiles, tile (x, y)
counted from the north-west corner (−180°, 90°). Each tile is a SIZE×SIZE grid of
heights (m, areoid-referenced like the DTMs) sampled at the tile's corners and edges,
row-major from north-west, float32 little-endian.

Sources, best first:
  1. the dataset's analysis grid (HiRISE + USGS gap fill, 5 m) — bilinear;
  2. MOLA 463 m around Gale, then MOLA at 1/8° globally (data/terrain_context.npz,
     built by scripts/build_terrain_context.py).
Within BLEND_M of the analysis-grid edge the two are blended linearly so the 5 m
patch meets MOLA without a wall. Coordinates: planetocentric, east-positive, on the
IAU Mars sphere — the same convention as every other layer.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np

SIZE = 65
BLEND_M = 300.0


class TerrainContext:
    """MOLA regional + global heights (int16 m)."""

    def __init__(self, path: Path):
        d = np.load(path)
        self.regional = d["regional"].astype(np.float32)
        self.reg_west = float(d["regional_west"])
        self.reg_north = float(d["regional_north"])
        self.reg_px = float(d["regional_px_deg"])
        self.glob = d["global_"].astype(np.float32)
        self.glob_px = float(d["global_px_deg"])
        self.source = str(d["source"])

    @staticmethod
    def _bilinear(a: np.ndarray, fr: np.ndarray, fc: np.ndarray, wrap_cols: bool) -> np.ndarray:
        h, w = a.shape
        fr = np.clip(fr, 0, h - 1)
        if wrap_cols:
            fc = np.mod(fc, w)
        else:
            fc = np.clip(fc, 0, w - 1)
        r0 = np.floor(fr).astype(int)
        c0 = np.floor(fc).astype(int)
        r1 = np.minimum(r0 + 1, h - 1)
        c1 = (c0 + 1) % w if wrap_cols else np.minimum(c0 + 1, w - 1)
        tr, tc = fr - r0, fc - c0
        top = a[r0, c0] * (1 - tc) + a[r0, c1] * tc
        bot = a[r1, c0] * (1 - tc) + a[r1, c1] * tc
        return top * (1 - tr) + bot * tr

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        # Pixel-centre coordinates: value at pixel (r, c) is at its centre.
        out = self._bilinear(self.glob, (90 - lat) / self.glob_px - 0.5,
                             (lon + 180) / self.glob_px - 0.5, wrap_cols=True)
        rh, rw = self.regional.shape
        fr = (self.reg_north - lat) / self.reg_px - 0.5
        fc = (lon - self.reg_west) / self.reg_px - 0.5
        inside = (fr >= 0) & (fr <= rh - 1) & (fc >= 0) & (fc <= rw - 1)
        if inside.any():
            out[inside] = self._bilinear(self.regional, fr[inside], fc[inside], wrap_cols=False)
        return out


def tile_lonlat(z: int, x: int, y: int, size: int = SIZE) -> tuple[np.ndarray, np.ndarray]:
    span = 180.0 / (1 << z)
    west, north = -180.0 + x * span, 90.0 - y * span
    t = np.linspace(0.0, 1.0, size)
    lon = west + t * span
    lat = north - t * span
    return np.meshgrid(lon, lat)


def valid_tile(z: int, x: int, y: int) -> bool:
    return 0 <= z <= 22 and 0 <= x < 2 * (1 << z) and 0 <= y < (1 << z)


def analysis_heights(ds, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bilinear heights from the 5 m analysis grid and the blend weight (0 outside)."""
    p, g = ds.proj, ds.grid
    k = p.radius * math.cos(math.radians(p.lat0))
    dlon = (lon - p.lon0 + 180.0) % 360.0 - 180.0
    xm = k * np.radians(dlon)
    ym = p.radius * np.radians(lat - p.lat0)
    x_max = g.x_min + g.width * g.cell
    y_min = g.y_max - g.height * g.cell
    edge = np.minimum.reduce([xm - g.x_min, x_max - xm, ym - y_min, g.y_max - ym])
    weight = np.clip(edge / BLEND_M, 0.0, 1.0)
    h = np.full(lon.shape, np.nan, dtype=np.float32)
    inside = edge > 0
    if inside.any():
        fc = (xm[inside] - g.x_min) / g.cell - 0.5
        fr = (g.y_max - ym[inside]) / g.cell - 0.5
        h[inside] = TerrainContext._bilinear(ds.elev, fr, fc, wrap_cols=False)
    weight[~np.isfinite(h)] = 0.0
    return h, weight


class TerrainTiler:
    def __init__(self, ds, context: TerrainContext | None):
        self.ds = ds
        self.context = context
        self._tile = lru_cache(maxsize=4096)(self._make)

    @property
    def available(self) -> bool:
        return self.context is not None

    def _make(self, z: int, x: int, y: int) -> bytes:
        lon, lat = tile_lonlat(z, x, y)
        base = self.context.sample(lon, lat) if self.context else np.zeros(lon.shape, np.float32)
        if self.ds.terrain_available and self.ds.proj is not None and self.ds.elev is not None:
            h, w = analysis_heights(self.ds, lon, lat)
            base = np.where(w > 0, w * np.nan_to_num(h) + (1 - w) * base, base)
        return base.astype("<f4").tobytes()

    def tile(self, z: int, x: int, y: int) -> bytes:
        return self._tile(z, x, y)
