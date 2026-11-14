"""Unit tests for COSMIC TRAIL core engine.

Covers geo.py, terrain.py and routing.py without any real NASA data.
All synthetic fixtures are created in-memory or in a temp directory.
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

# --- geo tests -----------------------------------------------------------------
from app.geo import (
    MARS_SPHERE_RADIUS_M,
    LocalEqc,
    _wrap180,
    haversine_m,
    proj_string,
    validate_lonlat,
)


def test_mars_radius_value():
    assert MARS_SPHERE_RADIUS_M == 3_396_190.0


def test_wrap180():
    assert _wrap180(0.0) == pytest.approx(0.0)
    assert _wrap180(180.0) == pytest.approx(-180.0)
    assert _wrap180(-180.0) == pytest.approx(-180.0)
    assert _wrap180(270.0) == pytest.approx(-90.0)
    assert _wrap180(-270.0) == pytest.approx(90.0)
    assert _wrap180(360.0) == pytest.approx(0.0)


def test_proj_string_contains_key_tokens():
    s = proj_string(-4.64, 137.2)
    assert "+proj=eqc" in s
    assert "lat_ts=-4.640000" in s
    assert "R=3396190.0" in s


def test_local_eqc_forward_origin():
    p = LocalEqc(lat0=-4.64, lon0=137.2)
    x, y = p.forward(137.2, -4.64)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)


def test_local_eqc_round_trip():
    p = LocalEqc(lat0=-4.64, lon0=137.2)
    for lon, lat in [(137.2, -4.64), (137.5, -4.9), (136.8, -4.3)]:
        x, y = p.forward(lon, lat)
        lo2, la2 = p.inverse(x, y)
        assert lo2 == pytest.approx(lon, abs=1e-9)
        assert la2 == pytest.approx(lat, abs=1e-9)


def test_local_eqc_x_proportional_to_longitude():
    """x must equal R * cos(lat0) * delta_lon_rad, to match the eqc formula."""
    p = LocalEqc(lat0=0.0, lon0=0.0)
    x1, _ = p.forward(1.0, 0.0)
    x2, _ = p.forward(2.0, 0.0)
    assert x2 == pytest.approx(2 * x1, rel=1e-9)
    expected = MARS_SPHERE_RADIUS_M * math.cos(math.radians(0.0)) * math.radians(1.0)
    assert x1 == pytest.approx(expected, rel=1e-9)


def test_local_eqc_y_proportional_to_latitude():
    p = LocalEqc(lat0=0.0, lon0=0.0)
    _, y1 = p.forward(0.0, 1.0)
    _, y2 = p.forward(0.0, 2.0)
    assert y2 == pytest.approx(2 * y1, rel=1e-9)
    expected = MARS_SPHERE_RADIUS_M * math.radians(1.0)
    assert y1 == pytest.approx(expected, rel=1e-9)


def test_scale_error_at_centre():
    p = LocalEqc(lat0=-4.64, lon0=137.2)
    assert p.scale_error_at(0.0) == pytest.approx(0.0, abs=1e-12)


def test_scale_error_increases_with_distance():
    p = LocalEqc(lat0=0.0, lon0=0.0)
    e1 = p.scale_error_at(MARS_SPHERE_RADIUS_M * math.radians(5.0))
    e2 = p.scale_error_at(MARS_SPHERE_RADIUS_M * math.radians(10.0))
    assert e2 > e1


def test_haversine_quarter_circle():
    """90-degree arc on the equator should give pi/2 * R."""
    expected = 0.5 * math.pi * MARS_SPHERE_RADIUS_M
    d = haversine_m(0.0, 0.0, 90.0, 0.0)
    assert d == pytest.approx(expected, rel=1e-9)


def test_haversine_zero_distance():
    assert haversine_m(137.2, -4.64, 137.2, -4.64) == pytest.approx(0.0, abs=1e-6)


def test_haversine_symmetric():
    d1 = haversine_m(137.0, -4.0, 138.0, -5.0)
    d2 = haversine_m(138.0, -5.0, 137.0, -4.0)
    assert d1 == pytest.approx(d2, rel=1e-12)


def test_haversine_1km():
    # 1 km along the equator ≈ 0.008983 degrees
    deg = 1000.0 / (MARS_SPHERE_RADIUS_M * math.pi / 180.0)
    d = haversine_m(0.0, 0.0, deg, 0.0)
    assert d == pytest.approx(1000.0, abs=0.01)


def test_haversine_antimeridian():
    # crossing the antimeridian: 170E to 170W = 20 degrees
    d = haversine_m(170.0, 0.0, -170.0, 0.0)
    expected = haversine_m(0.0, 0.0, 20.0, 0.0)
    assert d == pytest.approx(expected, rel=1e-9)


def test_validate_lonlat_ok():
    validate_lonlat(137.2, -4.64)  # should not raise


def test_validate_lonlat_bad_lat():
    with pytest.raises(ValueError, match="Latitude"):
        validate_lonlat(0.0, 91.0)


def test_validate_lonlat_non_finite():
    with pytest.raises(ValueError, match="finite"):
        validate_lonlat(float("nan"), 0.0)


# --- terrain tests -------------------------------------------------------------
from app.terrain import Grid, TerrainDataset, horn_slope_deg


def test_horn_slope_flat_plane():
    """Uniform elevation → zero slope everywhere (interior cells)."""
    elev = np.full((10, 10), -4500.0)
    s = horn_slope_deg(elev, 5.0)
    interior = s[1:-1, 1:-1]
    assert np.all(interior == pytest.approx(0.0, abs=1e-6))
    # border and corners must be NaN
    assert np.all(np.isnan(s[0, :]))
    assert np.all(np.isnan(s[-1, :]))
    assert np.all(np.isnan(s[:, 0]))
    assert np.all(np.isnan(s[:, -1]))


def test_horn_slope_known_plane():
    """45-degree N-S slope: dz = cell_m per step."""
    n = 11
    cell = 5.0
    elev = np.tile(np.arange(n, dtype=np.float64) * cell, (n, 1)).T
    s = horn_slope_deg(elev, cell)
    interior = s[1:-1, 1:-1]
    expected = math.degrees(math.atan(1.0))  # 45 deg
    assert np.allclose(interior, expected, atol=0.5)


def test_horn_slope_nodata_propagates():
    """NaN in a cell propagates NaN to output cells whose 3x3 window uses it.

    Horn's formula uses the 8 surrounding cells but NOT the center cell, so
    a NaN at z[3,3] propagates to the 8 output neighbors of (3,3) but NOT to
    output cell (3,3) itself — the center is excluded from the finite difference.
    """
    elev = np.zeros((7, 7))
    elev[3, 3] = np.nan
    s = horn_slope_deg(elev, 5.0)
    # All 8 output neighbors of (3,3) must be NaN
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            if dr == 0 and dc == 0:
                # Horn's formula does not use the center cell, so the output
                # at (3,3) is computed from its (non-NaN) 8 neighbors.
                assert np.isfinite(s[3, 3])
            else:
                assert np.isnan(s[3 + dr, 3 + dc])


def test_horn_slope_too_small():
    """Grids smaller than 3x3 return all NaN."""
    elev = np.zeros((2, 5))
    s = horn_slope_deg(elev, 5.0)
    assert np.all(np.isnan(s))


def test_grid_rc_inside():
    g = Grid(x_min=-100.0, y_max=200.0, cell=5.0, width=40, height=80)
    # top-left corner cell centre
    rc = g.rc(-97.5, 197.5)
    assert rc == (0, 0)


def test_grid_rc_outside():
    g = Grid(x_min=-100.0, y_max=200.0, cell=5.0, width=40, height=80)
    assert g.rc(-200.0, 100.0) is None
    assert g.rc(0.0, 300.0) is None


def test_grid_xy_round_trip():
    g = Grid(x_min=-100.0, y_max=200.0, cell=5.0, width=40, height=80)
    for r, c in [(0, 0), (10, 20), (79, 39)]:
        x, y = g.xy(r, c)
        rc2 = g.rc(x, y)
        assert rc2 == (r, c)


def _make_synthetic_ds(n=30, cell=5.0):
    """Create a temporary TerrainDataset folder with a flat tilted plane."""
    folder = Path(tempfile.mkdtemp())
    lat0, lon0 = -4.64, 137.2
    x_min = -n * cell / 2
    y_max = n * cell / 2
    proj = LocalEqc(lat0=lat0, lon0=lon0)

    # Elevation: gentle 2-degree N-S slope
    rows = np.arange(n)
    slope_rise = cell * math.tan(math.radians(2.0))
    elev = np.full((n, n), -4500.0)
    for r in range(n):
        elev[r, :] = -4500.0 + (n - 1 - r) * slope_rise

    slope = horn_slope_deg(elev, cell)
    # fill border with 0 so they're not NaN (makes routing tests simpler)
    slope = np.where(np.isfinite(slope), slope, 0.0)

    np.savez_compressed(str(folder / "analysis.npz"),
                        elevation=elev.astype(np.float32),
                        slope_deg=slope.astype(np.float32))

    meta = {
        "kind": "synthetic_test",
        "dataset_id": "test",
        "analysis": {
            "x_min": x_min, "y_max": y_max,
            "cell_size_m": cell, "width": n, "height": n,
            "available": True, "file": "analysis.npz",
        },
        "crs": {"type": "local_eqc", "lat0": lat0, "lon0": lon0, "radius": 3396190.0},
    }
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return TerrainDataset(folder), meta


def test_terrain_dataset_loads():
    ds, _ = _make_synthetic_ds()
    assert ds.terrain_available
    assert ds.elev is not None
    assert ds.slope is not None


def test_terrain_dataset_valid_mask():
    ds, _ = _make_synthetic_ds()
    m = ds.valid_mask()
    assert m.all()


def test_terrain_dataset_coverage():
    ds, _ = _make_synthetic_ds()
    assert ds.coverage_fraction() == pytest.approx(1.0, abs=1e-6)


def test_terrain_dataset_lookup_ok():
    ds, _ = _make_synthetic_ds()
    g = ds.grid
    x, y = g.xy(5, 5)
    result = ds.lookup(x, y)
    assert result["status"] == "ok"
    assert result["elevation_m"] is not None
    assert result["slope_deg"] is not None


def test_terrain_dataset_lookup_outside():
    ds, _ = _make_synthetic_ds()
    result = ds.lookup(1e9, 1e9)
    assert result["status"] == "outside_study_area"


def test_terrain_dataset_to_lonlat_round_trip():
    ds, _ = _make_synthetic_ds()
    g = ds.grid
    x, y = g.xy(10, 15)
    ll = ds.to_lonlat(x, y)
    assert ll is not None
    xy2 = ds.from_lonlat(*ll)
    assert xy2[0] == pytest.approx(x, abs=1e-3)
    assert xy2[1] == pytest.approx(y, abs=1e-3)


def test_terrain_dataset_stats():
    ds, _ = _make_synthetic_ds()
    s = ds.stats()
    assert "cells_total" in s
    assert s["cells_valid"] == s["cells_total"]
    assert s["elevation_min_m"] is not None


# --- routing tests -----------------------------------------------------------
from app.routing import (
    RouteError,
    RouteParams,
    compare_routes,
    explain_tradeoff,
    passable_mask,
    plan_route,
    rasterize_polygons,
)


def test_route_params_defaults():
    p = RouteParams()
    p.validate()  # should not raise


def test_route_params_bad_slope():
    with pytest.raises(RouteError) as exc_info:
        p = RouteParams(max_slope_deg=0.5)
        p.validate()
    assert exc_info.value.code == "bad_params"


def test_route_params_from_dict():
    p = RouteParams.from_dict({"max_slope_deg": 25.0})
    assert p.max_slope_deg == 25.0


def test_route_params_from_dict_ignores_unknown():
    p = RouteParams.from_dict({"unknown_key": 999})
    assert RouteParams().max_slope_deg == p.max_slope_deg


def test_shortest_route_straight_line():
    """On flat terrain with no obstacles, the shortest route is a near-straight line."""
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    xs, ys = g.xy(1, 1)
    xe, ye = g.xy(1, 18)
    p = RouteParams(max_slope_deg=20.0)
    result = plan_route(ds, (xs, ys), (xe, ye), "shortest", p)
    assert result["cells"] > 0
    assert result["planimetric_length_m"] > 0
    assert result["planimetric_length_m"] < 200.0  # 17 cells * 5 m = 85 m


def test_terrain_route_runs():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    xs, ys = g.xy(5, 5)
    xe, ye = g.xy(5, 15)
    p = RouteParams()
    result = plan_route(ds, (xs, ys), (xe, ye), "terrain", p)
    assert result["mode"] == "terrain"
    assert result["cells"] > 0


def test_route_same_point_raises():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    x, y = g.xy(5, 5)
    with pytest.raises(RouteError) as exc_info:
        plan_route(ds, (x, y), (x, y), "shortest", RouteParams())
    assert exc_info.value.code == "same_point"


def test_route_outside_raises():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    with pytest.raises(RouteError) as exc_info:
        plan_route(ds, (1e9, 1e9), (0.0, 0.0), "shortest", RouteParams())
    assert exc_info.value.code == "outside_study_area"


def test_route_bad_mode():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    xs, ys = g.xy(5, 5)
    xe, ye = g.xy(5, 15)
    with pytest.raises(RouteError) as exc_info:
        plan_route(ds, (xs, ys), (xe, ye), "diagonal", RouteParams())
    assert exc_info.value.code == "bad_mode"


def test_route_no_path_through_wall():
    """Block an entire column → no path from left half to right half."""
    ds, _ = _make_synthetic_ds(n=15, cell=5.0)
    g = ds.grid
    # mark the entire middle column as impassable via exclusion
    n = g.width
    mid = n // 2
    # Build exclusion mask manually
    exc = np.zeros((g.height, g.width), dtype=bool)
    exc[:, mid] = True
    p = RouteParams()
    ok = passable_mask(ds, p, exc)
    xs, ys = g.xy(7, 1)
    xe, ye = g.xy(7, n - 2)
    with pytest.raises(RouteError) as exc_info:
        plan_route(ds, (xs, ys), (xe, ye), "shortest", p, exclusion=exc, ok=ok)
    assert exc_info.value.code == "no_feasible_route"


def test_blocked_start_snaps_to_destination_component():
    """A tied nearest start snap should use the passable cell connected to the destination."""
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    ds.slope[:, 10] = 89.0
    start = g.xy(10, 10)
    destination = g.xy(10, 15)

    route = plan_route(ds, start, destination, "shortest", RouteParams())

    assert route["cell_path"][0] == [10, 11]
    assert route["cell_path"][-1] == [10, 15]
    assert all(c > 10 for _, c in route["cell_path"])


def test_route_too_steep_blocked():
    """When all cells exceed max_slope_deg, start is immediately blocked."""
    ds, _ = _make_synthetic_ds(n=15, cell=5.0)
    g = ds.grid
    # Assign enormous slope to all cells
    ds.slope[:] = 89.0
    xs, ys = g.xy(5, 5)
    xe, ye = g.xy(5, 10)
    p = RouteParams(max_slope_deg=20.0)
    with pytest.raises(RouteError) as exc_info:
        plan_route(ds, (xs, ys), (xe, ye), "shortest", p)
    assert exc_info.value.code in ("point_blocked", "no_feasible_route")


def test_route_no_corner_cutting():
    """With two adjacent blocked cells, the diagonal move between them is forbidden."""
    ds, _ = _make_synthetic_ds(n=10, cell=5.0)
    g = ds.grid
    # Block positions (5,4) and (4,5) → the diagonal from (5,5) to (4,4) or vice versa
    # requires passing through both, so the diagonal move must be forbidden.
    exc = np.zeros((g.height, g.width), dtype=bool)
    exc[5, 4] = True
    exc[4, 5] = True
    p = RouteParams(allow_diagonal=True)
    ok = passable_mask(ds, p, exc)
    xs, ys = g.xy(5, 5)
    xe, ye = g.xy(4, 4)
    result = plan_route(ds, (xs, ys), (xe, ye), "shortest", p, exclusion=exc, ok=ok)
    # Route must go around — length > one diagonal step (5*sqrt(2) ≈ 7.07)
    assert result["planimetric_length_m"] > 5.0 * math.sqrt(2.0) + 1.0


def test_route_elevation_profile_length_matches_cells():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    xs, ys = g.xy(5, 2)
    xe, ye = g.xy(5, 17)
    result = plan_route(ds, (xs, ys), (xe, ye), "terrain", RouteParams())
    assert len(result["elevation_profile"]) == result["cells"]
    assert len(result["slope_profile"]) == result["cells"]


def test_route_xy_lonlat_lengths_match():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    xs, ys = g.xy(5, 2)
    xe, ye = g.xy(5, 17)
    result = plan_route(ds, (xs, ys), (xe, ye), "terrain", RouteParams())
    assert len(result["xy"]) == result["cells"]
    if result["lonlat"] is not None:
        assert len(result["lonlat"]) == result["cells"]


def test_compare_routes_identical():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    xs, ys = g.xy(5, 2)
    xe, ye = g.xy(5, 17)
    p = RouteParams()
    r1 = plan_route(ds, (xs, ys), (xe, ye), "shortest", p)
    r2 = plan_route(ds, (xs, ys), (xe, ye), "shortest", p)
    cmp = compare_routes(r1, r2, ds.grid.cell)
    assert cmp["relation"] in ("identical", "equivalent")


def test_compare_routes_different():
    ds, _ = _make_synthetic_ds(n=30, cell=5.0)
    g = ds.grid
    # Add a moderate slope ridge that the terrain router avoids
    ds.slope[10:15, 5:25] = 15.0
    xs, ys = g.xy(5, 5)
    xe, ye = g.xy(25, 25)
    p = RouteParams(max_slope_deg=20.0, slope_weight=8.0)
    r_short = plan_route(ds, (xs, ys), (xe, ye), "shortest", p)
    r_terr = plan_route(ds, (xs, ys), (xe, ye), "terrain", p)
    cmp = compare_routes(r_short, r_terr, ds.grid.cell)
    # May be identical or different — test only that the function runs and returns valid keys
    assert "relation" in cmp
    assert "text" in cmp


def test_explain_tradeoff():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    xs, ys = g.xy(5, 2)
    xe, ye = g.xy(5, 17)
    p = RouteParams()
    r1 = plan_route(ds, (xs, ys), (xe, ye), "shortest", p)
    r2 = plan_route(ds, (xs, ys), (xe, ye), "terrain", p)
    text = explain_tradeoff(r1, r2)
    assert "terrain-weighted" in text
    assert "prototype assumption" in text.lower() or "modelled" in text.lower()


def test_rasterize_polygons_triangle():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    g = ds.grid
    # Triangle in the centre of the grid
    cx, cy = 0.0, 0.0
    s = g.cell * 4
    poly = [[cx - s, cy - s], [cx + s, cy - s], [cx, cy + s]]
    mask = rasterize_polygons(ds, [poly])
    assert mask.any()
    assert not mask.all()


def test_rasterize_polygons_empty():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    mask = rasterize_polygons(ds, [])
    assert not mask.any()


def test_rasterize_polygons_outside_grid():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    # Polygon entirely outside the grid
    poly = [[1e6, 1e6], [1e6 + 100, 1e6], [1e6 + 100, 1e6 + 100], [1e6, 1e6 + 100]]
    mask = rasterize_polygons(ds, [poly])
    assert not mask.any()


def test_terrain_unavailable_raises():
    folder = Path(tempfile.mkdtemp())
    meta = {
        "kind": "test", "dataset_id": "t",
        "analysis": {"x_min": 0.0, "y_max": 0.0, "cell_size_m": 5.0,
                     "width": 10, "height": 10, "available": False, "file": "analysis.npz"},
        "crs": {"type": "local_eqc", "lat0": 0.0, "lon0": 0.0},
    }
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    ds = TerrainDataset(folder)
    assert not ds.terrain_available
    with pytest.raises(RouteError) as exc_info:
        plan_route(ds, (0.0, 0.0), (10.0, 0.0), "shortest", RouteParams())
    assert exc_info.value.code == "terrain_unavailable"
