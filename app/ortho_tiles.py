"""HiRISE orthoimage served as globe imagery tiles (Cesium UrlTemplateImageryProvider).

Tiling: the same Cesium GeographicTilingScheme as the height tiles (app/terrain_tiles.py)
and the Mars Trek basemap: level z has 2·2^z × 2^z tiles, tile (x, y) counted from the
north-west corner (−180°, 90°). Tiles are 256×256 greyscale+alpha PNGs.

The source is the HiRISE RDR ortho JP2 (e.g. ESP_024234_1755_RED_C_01_ORTHO.JP2): 8-bit,
~1 m/px, equirectangular on the Mars sphere R = 3 396 190 m. Equirectangular is linear in
lon/lat, so every geographic tile maps to an axis-aligned pixel window of the source and is
read directly with GDAL (no warping). GDAL picks the JPEG2000 resolution level that fits
the request, so zoomed-out tiles stay cheap. Pixel value 0 is the image's no-data collar
and becomes transparent; the rest gets one tone curve for the whole image.

Tiles are rendered on demand and kept in an in-memory LRU cache.
"""
from __future__ import annotations

import io
import math
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

TILE = 256
MAX_LEVEL_CAP = 22


def _png(gray: np.ndarray, alpha: np.ndarray) -> bytes:
    from PIL import Image
    img = Image.fromarray(np.dstack([gray, alpha]), mode="LA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def _tone_lut(sample: np.ndarray) -> np.ndarray:
    """8-bit → 8-bit lookup: 0 stays 0 (no data), valid pixels map to 1…255."""
    hist = np.bincount(sample[sample > 0].ravel(), minlength=256)[:256].astype(np.float64)
    hist[0] = 0
    levels = np.arange(256, dtype=np.float64)
    if hist.sum() > 0:
        cdf = np.cumsum(hist) / hist.sum()
        out = 0.5 * (1 + 254 * cdf) + 0.5 * levels
    else:
        out = levels
    lut = np.clip(np.round(out), 1, 255).astype(np.uint8)
    lut[0] = 0
    return lut


def _erode(valid: np.ndarray) -> np.ndarray:
    """Drop a 1-px rim at the no-data edge, where resampling blends in the black collar."""
    out = valid.copy()
    out[1:, :] &= valid[:-1, :]
    out[:-1, :] &= valid[1:, :]
    out[:, 1:] &= valid[:, :-1]
    out[:, :-1] &= valid[:, 1:]
    return out


EMPTY_PNG = _png(np.zeros((TILE, TILE), np.uint8), np.zeros((TILE, TILE), np.uint8))


class OrthoTiler:
    def __init__(self, path: Path, credit: str = "NASA/JPL-Caltech/UArizona", cache_size: int = 2048):
        import rasterio
        from pyproj import CRS, Transformer

        self.path = Path(path)
        self.credit = credit
        self._local = threading.local()
        with rasterio.open(self.path) as src:
            if src.crs is None:
                raise ValueError(f"{self.path.name} has no CRS")
            crs = CRS.from_wkt(src.crs.to_wkt())
            method = crs.coordinate_operation.method_name if crs.coordinate_operation else None
            m = (method or "").lower()
            if "equidistant cylindrical" not in m and "equirectangular" not in m:
                raise ValueError(f"{self.path.name}: expected an equirectangular CRS, got {method!r}")
            self.width, self.height = src.width, src.height
            if src.dtypes[0] != "uint8":
                raise ValueError(f"{self.path.name}: expected 8-bit pixels, got {src.dtypes[0]}")
            b = src.bounds
            # Same sphere, planetocentric lon/lat: eqc → lon/lat is linear, so the corners suffice.
            to_ll = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
            self.west, self.north = to_ll.transform(b.left, b.top)
            self.east, self.south = to_ll.transform(b.right, b.bottom)
            self.res_m = float(src.res[0])
            # One tone curve for the whole image, from a coarse resolution level, so every tile
            # matches: half histogram equalisation, half identity. HiRISE RED orthos pack most
            # terrain into a narrow bright band (here ~178–223 of 255) with a long dark tail;
            # a linear stretch would clip the shadows, full equalisation looks harsh.
            f = max(1, max(self.width, self.height) // 1024)
            thumb = src.read(1, out_shape=(max(1, self.height // f), max(1, self.width // f)))
            self.lut = _tone_lut(thumb)
        self.px_lon = (self.east - self.west) / self.width    # degrees per source pixel
        self.px_lat = (self.north - self.south) / self.height
        # Deepest level whose tile pixels are still at least as fine as the source pixels.
        self.max_level = min(MAX_LEVEL_CAP, math.ceil(math.log2(180.0 / (TILE * self.px_lon))))
        self._cached = lru_cache(maxsize=cache_size)(self._render)

    # One GDAL handle per worker thread (GDAL datasets are not thread-safe).
    def _src(self):
        src = getattr(self._local, "src", None)
        if src is None:
            import rasterio
            src = self._local.src = rasterio.open(self.path)
        return src

    def info(self) -> dict:
        return {
            "available": True,
            "file": self.path.name,
            "west": self.west, "south": self.south, "east": self.east, "north": self.north,
            "resolution_m": round(self.res_m, 3),
            "max_level": self.max_level,
            "tile_size": TILE,
            "credit": self.credit,
        }

    def tile(self, z: int, x: int, y: int) -> bytes:
        return self._cached(z, x, y)

    def _render(self, z: int, x: int, y: int) -> bytes:
        from rasterio.enums import Resampling
        from rasterio.windows import Window

        span = 180.0 / (1 << z)
        west, north = -180.0 + x * span, 90.0 - y * span
        east, south = west + span, north - span
        if east <= self.west or west >= self.east or north <= self.south or south >= self.north:
            return EMPTY_PNG

        # Tile edges in fractional source-pixel coordinates.
        c0 = (west - self.west) / self.px_lon
        c1 = (east - self.west) / self.px_lon
        r0 = (self.north - north) / self.px_lat
        r1 = (self.north - south) / self.px_lat
        cc0, cc1 = max(c0, 0.0), min(c1, float(self.width))
        rr0, rr1 = max(r0, 0.0), min(r1, float(self.height))
        # Where that clipped window lands inside the 256×256 tile.
        sx, sy = TILE / (c1 - c0), TILE / (r1 - r0)
        dx0, dx1 = round((cc0 - c0) * sx), round((cc1 - c0) * sx)
        dy0, dy1 = round((rr0 - r0) * sy), round((rr1 - r0) * sy)
        if dx1 <= dx0 or dy1 <= dy0:
            return EMPTY_PNG

        data = self._src().read(
            1,
            window=Window(cc0, rr0, cc1 - cc0, rr1 - rr0),
            out_shape=(dy1 - dy0, dx1 - dx0),
            resampling=Resampling.bilinear,
        )
        gray = np.zeros((TILE, TILE), np.uint8)
        alpha = np.zeros((TILE, TILE), np.uint8)
        gray[dy0:dy1, dx0:dx1] = self.lut[data]
        alpha[dy0:dy1, dx0:dx1] = np.where(_erode(data > 0), 255, 0)
        return _png(gray, alpha)
