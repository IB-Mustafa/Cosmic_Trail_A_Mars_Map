"""Terrain grid loading, slope computation and point lookups."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geo import LocalEqc


def horn_slope_deg(elev: np.ndarray, cell_size_m: float) -> np.ndarray:
    """Slope in degrees using Horn's (1981) 3x3 finite-difference method.

    ``elev`` is a 2-D array of elevations in metres with NaN for NoData.
    ``cell_size_m`` is the horizontal cell size in metres (same units as elev).
    Any cell whose 3x3 neighbourhood touches NoData, or which lies on the grid
    border, gets NaN ("unknown") - it is never treated as flat.
    """
    if cell_size_m <= 0:
        raise ValueError("cell_size_m must be positive")
    z = np.asarray(elev, dtype=np.float64)
    out = np.full(z.shape, np.nan, dtype=np.float64)
    if z.shape[0] < 3 or z.shape[1] < 3:
        return out.astype(np.float32)
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8.0 * cell_size_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8.0 * cell_size_m)
    out[1:-1, 1:-1] = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    return out.astype(np.float32)


@dataclass
class Grid:
    """Raster grid geometry in the local metric CRS (north-up)."""

    x_min: float
    y_max: float
    cell: float
    width: int
    height: int

    @property
    def x_max(self) -> float:
        return self.x_min + self.cell * self.width

    @property
    def y_min(self) -> float:
        return self.y_max - self.cell * self.height

    def rc(self, x: float, y: float) -> tuple[int, int] | None:
        if not (self.x_min <= x < self.x_max and self.y_min < y <= self.y_max):
            return None
        c = int((x - self.x_min) // self.cell)
        r = int((self.y_max - y) // self.cell)
        if 0 <= r < self.height and 0 <= c < self.width:
            return r, c
        return None

    def xy(self, r: int, c: int) -> tuple[float, float]:
        return (self.x_min + (c + 0.5) * self.cell, self.y_max - (r + 0.5) * self.cell)


class TerrainDataset:
    """A processed dataset folder (see scripts/prepare_data.py)."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        meta_path = self.folder / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No metadata.json in {self.folder}")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        a = self.meta["analysis"]
        self.grid = Grid(a["x_min"], a["y_max"], a["cell_size_m"], a["width"], a["height"])
        self.elev = None
        self.slope = None
        self.mola_filled = None   # True where elevation came from MOLA gap fill
        self.usgs_filled = None   # True where elevation came from USGS Gale DEM gap fill
        self.terrain_available = bool(a.get("available", True))
        npz = self.folder / a.get("file", "analysis.npz")
        if self.terrain_available and npz.exists():
            with np.load(npz) as data:
                self.elev = data["elevation"].astype(np.float32)
                self.slope = data["slope_deg"].astype(np.float32)
                if "mola_filled" in data.files:
                    self.mola_filled = data["mola_filled"].astype(bool)
                if "usgs_filled" in data.files:
                    self.usgs_filled = data["usgs_filled"].astype(bool)
            if self.elev.shape != (self.grid.height, self.grid.width):
                raise ValueError("analysis grid shape does not match metadata")
        else:
            self.terrain_available = False
        crs = self.meta.get("crs", {})
        self.proj = LocalEqc(crs["lat0"], crs["lon0"], crs.get("radius", 3396190.0)) \
            if crs.get("type") == "local_eqc" else None

    # ------------------------------------------------------------------ info
    @property
    def kind(self) -> str:
        return self.meta.get("kind", "unknown")

    @property
    def dataset_id(self) -> str:
        return self.meta.get("dataset_id", self.folder.name)

    def valid_mask(self) -> np.ndarray:
        """True where elevation AND slope are known."""
        return np.isfinite(self.elev) & np.isfinite(self.slope)

    def coverage_fraction(self) -> float:
        if not self.terrain_available:
            return 0.0
        return float(self.valid_mask().mean())

    # ---------------------------------------------------------------- lookup
    def to_lonlat(self, x: float, y: float) -> tuple[float, float] | None:
        return self.proj.inverse(x, y) if self.proj else None

    def from_lonlat(self, lon: float, lat: float) -> tuple[float, float]:
        if not self.proj:
            raise ValueError("This dataset has no planetary coordinate system (synthetic demo).")
        return self.proj.forward(lon, lat)

    def lookup(self, x: float, y: float) -> dict:
        """Values at a map position, with explicit status for every case."""
        out: dict = {"x": x, "y": y, "in_study_area": False, "status": "outside_study_area"}
        ll = self.to_lonlat(x, y)
        if ll:
            out["lon"], out["lat"] = round(ll[0], 6), round(ll[1], 6)
        if not self.terrain_available:
            out["status"] = "terrain_unavailable"
            return out
        rc = self.grid.rc(x, y)
        if rc is None:
            return out
        r, c = rc
        out["in_study_area"] = True
        out["row"], out["col"] = r, c
        e, s = float(self.elev[r, c]), float(self.slope[r, c])
        out["elevation_m"] = round(e, 2) if math.isfinite(e) else None
        out["slope_deg"] = round(s, 2) if math.isfinite(s) else None
        if math.isfinite(e) and self.kind != "synthetic_demo":
            if self.usgs_filled is not None and bool(self.usgs_filled[r, c]):
                out["elevation_source"] = "USGS Gale DEM (gap fill)"
            elif self.mola_filled is not None and bool(self.mola_filled[r, c]):
                out["elevation_source"] = "MOLA 463 m (gap fill)"
            else:
                out["elevation_source"] = "HiRISE"
        if not math.isfinite(e):
            out["status"] = "nodata"
        elif not math.isfinite(s):
            out["status"] = "slope_unknown"
        else:
            out["status"] = "ok"
        return out

    def stats(self) -> dict:
        if not self.terrain_available:
            return {}
        v = self.valid_mask()
        e = self.elev[np.isfinite(self.elev)]
        s = self.slope[v]
        return {
            "cells_total": int(v.size),
            "cells_valid": int(v.sum()),
            "coverage_fraction": round(float(v.mean()), 4),
            "elevation_min_m": round(float(e.min()), 2) if e.size else None,
            "elevation_max_m": round(float(e.max()), 2) if e.size else None,
            "slope_median_deg": round(float(np.median(s)), 2) if s.size else None,
            "slope_p95_deg": round(float(np.percentile(s, 95)), 2) if s.size else None,
        }
