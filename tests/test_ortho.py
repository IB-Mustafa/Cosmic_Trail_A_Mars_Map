"""HiRISE photo layer: tile pyramid depth, a sharper mosaic with a 1 m fallback, cache headers.

All mosaics here are small synthetic GeoTIFFs in a temp directory (eqc on the Mars sphere, the
same convention as scripts/build_ortho_mosaic.py), so no NASA data is needed.
"""
from __future__ import annotations

import io
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.ortho_tiles import TILE, OrthoTiler

MARS_R = 3396190.0
WINDOW = (137.43, 137.45, -4.60, -4.58)          # ~1.2 km × 1.2 km around Bradbury Landing
LON0 = (WINDOW[0] + WINDOW[1]) / 2
K = math.pi / 180 * MARS_R                       # metres per degree


def _write(path: Path, res_m: float, fill) -> Path:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds

    lon_min, lon_max, lat_min, lat_max = WINDOW
    left, right = (lon_min - LON0) * K, (lon_max - LON0) * K
    bottom, top = lat_min * K, lat_max * K
    w, h = round((right - left) / res_m), round((top - bottom) / res_m)
    data = fill(h, w).astype(np.uint8)
    crs = CRS.from_proj4(f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0={LON0} +x_0=0 +y_0=0 +R={MARS_R} +units=m +no_defs")
    with rasterio.open(path, "w", driver="GTiff", width=w, height=h, count=1, dtype="uint8", crs=crs,
                       transform=from_bounds(left, bottom, right, top, w, h), nodata=0, tiled=True,
                       blockxsize=256, blockysize=256) as dst:
        dst.write(data, 1)
        dst.update_tags(SOURCES="A_ORTHO.JP2,B_ORTHO.JP2")
    return path


def _tile_xy(z: int, lon: float, lat: float) -> tuple[int, int]:
    span = 180.0 / (1 << z)
    return int((lon + 180) / span), int((90 - lat) / span)


def _rgba(png: bytes):
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    a = np.asarray(im.convert("LA"))
    return a[..., 0], a[..., 1]


@pytest.fixture(scope="module")
def mosaics(tmp_path_factory):
    d = tmp_path_factory.mktemp("ortho")
    rng = np.random.default_rng(0)
    one_m = _write(d / "ortho_mosaic.tif", 1.0, lambda h, w: rng.integers(150, 230, (h, w)))
    # The 0.5 m mosaic covers only the western half (a partial download): the rest is 0 = no data.
    def west_half(h, w):
        a = rng.integers(150, 230, (h, w))
        a[:, w // 2:] = 0
        return a
    half_m = _write(d / "ortho_mosaic_50cm.tif", 0.5, west_half)
    return d, one_m, half_m


def test_pyramid_goes_down_to_the_native_resolution(mosaics):
    _, one_m, half_m = mosaics
    for path, res in ((one_m, 1.0), (half_m, 0.5)):
        t = OrthoTiler(path)
        tile_m = 180.0 / (1 << t.max_level) / TILE * K
        coarser_m = 180.0 / (1 << (t.max_level - 1)) / TILE * K
        # The deepest level is the first one whose tile pixels are at least as fine as the data.
        assert tile_m <= res < coarser_m, (path.name, tile_m, coarser_m)
    assert OrthoTiler(half_m).max_level == OrthoTiler(one_m).max_level + 1


def test_fine_mosaic_with_fallback_has_no_holes(mosaics):
    _, one_m, half_m = mosaics
    fb = OrthoTiler(one_m)
    fine = OrthoTiler(half_m, fallback=fb)
    alone = OrthoTiler(half_m)
    z = fine.max_level - 3
    x, y = _tile_xy(z, (WINDOW[0] + WINDOW[1]) / 2, (WINDOW[2] + WINDOW[3]) / 2)
    _, a_alone = _rgba(alone.tile(z, x, y))
    _, a_fine = _rgba(fine.tile(z, x, y))
    _, a_fb = _rgba(fb.tile(z, x, y))
    assert (a_alone == 0).sum() > (a_fb == 0).sum()          # the half mosaic alone has a hole…
    assert (a_fine == 0).sum() == (a_fb == 0).sum()          # …which the 1 m mosaic fills exactly


def test_detail_grid_marks_where_the_fine_mosaic_has_data(mosaics):
    _, one_m, half_m = mosaics
    info = OrthoTiler(half_m, fallback=OrthoTiler(one_m)).info()
    assert info["resolution_m"] == 0.5 and info["fallback"]["resolution_m"] == 1.0
    g = info["detail_grid"]
    assert len(g["cells"]) == g["rows"] and all(len(r) == g["cols"] for r in g["cells"])
    west = "".join(r[: g["cols"] // 2 - 1] for r in g["cells"])
    east = "".join(r[g["cols"] // 2 + 1:] for r in g["cells"])
    assert set(west) == {"1"} and set(east) == {"0"}
    assert "fallback" not in OrthoTiler(one_m).info()          # the plain 1 m layer is unchanged


def test_sources_come_from_the_mosaic_tags(mosaics):
    _, one_m, _ = mosaics
    assert OrthoTiler(one_m).tag_sources == ["A_ORTHO.JP2", "B_ORTHO.JP2"]


def test_backend_prefers_the_sharpest_mosaic_present(mosaics):
    from app.main import _load_ortho
    d, one_m, half_m = mosaics
    meta = {"ortho": {"mosaic": one_m.name, "sources": ["X_RED_C_01_ORTHO.JP2"]}}
    tiler, note = _load_ortho(SimpleNamespace(folder=d, meta=meta))
    assert note is None and tiler.path.name == half_m.name and tiler.fallback.path.name == one_m.name
    assert tiler.res_m == pytest.approx(0.5, rel=1e-4)


def test_backend_uses_the_1m_mosaic_when_no_sharper_one_exists(tmp_path):
    from app.main import _load_ortho
    one = _write(tmp_path / "ortho_mosaic.tif", 1.0, lambda h, w: np.full((h, w), 200))
    tiler, note = _load_ortho(SimpleNamespace(folder=tmp_path, meta={"ortho": {"mosaic": one.name, "sources": ["S.JP2"]}}))
    assert note is None and tiler.path == one and tiler.fallback is None and tiler.sources == ["S.JP2"]
    missing, why = _load_ortho(SimpleNamespace(folder=tmp_path / "nothing", meta={"ortho": {"mosaic": "ortho_mosaic.tif"}}))
    assert missing is None and "not found" in why


def test_mosaic_names_for_each_resolution():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import build_ortho_mosaic as B
    assert B.mosaic_name(1.0) == "ortho_mosaic.tif" and B.metadata_key(1.0) == "ortho"
    assert B.mosaic_name(0.5) == "ortho_mosaic_50cm.tif" and B.metadata_key(0.5) == "ortho_hires"
    assert B.mosaic_name(0.25) == "ortho_mosaic_25cm.tif"
    assert all("_RED_A_" in n for n in B.HIRES_FILES) and len(B.HIRES_FILES) == len(B.ORTHO_FILES)


def test_tiles_are_cached_for_a_year_under_versioned_urls():
    from fastapi.testclient import TestClient
    from app import main
    if not main.DATASETS:
        main._load_datasets()
    if "hirise_gale" not in main.ORTHO:
        pytest.skip("hirise_gale ortho mosaic not present")
    c = TestClient(main.app)
    info = c.get("/api/datasets/hirise_gale/ortho").json()
    z = info["max_level"]
    x, y = _tile_xy(z, 137.4417, -4.5895)
    r = c.get(f"/api/datasets/hirise_gale/ortho/{z}/{x}/{y}.png?v={info['version']}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert "immutable" in r.headers["cache-control"] and "max-age=31536000" in r.headers["cache-control"]
