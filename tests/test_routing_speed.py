"""Fast route search (app/routing.py): the numba-compiled A*, walkable-region snapping and
the coarse-to-fine corridor search for long routes."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from app import routing as R
from app.routing import RouteError, RouteParams, plan_route

from tests.test_core import _make_synthetic_ds

pytestmark = pytest.mark.skipif(not R.HAVE_NUMBA, reason="numba not installed")

REAL = Path(__file__).resolve().parent.parent / "data" / "hirise_gale"


def _rough_ds(n=60, seed=0):
    """Synthetic grid with random steep patches so paths must detour."""
    ds, _ = _make_synthetic_ds(n=n, cell=5.0)
    rng = np.random.default_rng(seed)
    ds.slope[rng.random(ds.slope.shape) < 0.25] = 40.0
    ds.elev += rng.normal(0, 2.0, ds.elev.shape).astype(ds.elev.dtype)
    return ds


@pytest.mark.parametrize("mode", ["shortest", "terrain"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_compiled_astar_matches_python_reference(mode, seed):
    """Same cost model and rules: the compiled search finds a path of the same (optimal) cost,
    or reports the same reachable set when there is none."""
    ds = _rough_ds(seed=seed)
    p = RouteParams()
    ok = R.passable_mask(ds, p, None)
    cells = np.argwhere(ok)
    a, b = tuple(cells[0]), tuple(cells[-1])
    fast, _, reach_fast = R._astar(ok, ds.elev, ds.slope, 5.0, a, b, mode, p)
    ref, _, reach_ref = R._astar_py(ok, ds.elev, ds.slope, 5.0, a, b, mode, p)
    if ref is None:
        assert fast is None and bytes(reach_fast) == bytes(reach_ref)
        return
    m_fast = R.route_metrics(ds, fast, p, mode)
    m_ref = R.route_metrics(ds, ref, p, mode)
    key = "planimetric_length_m" if mode == "shortest" else "modelled_terrain_cost"
    assert m_fast[key] == pytest.approx(m_ref[key], abs=0.2)


def test_budgeted_search_stops_and_reports():
    ds = _rough_ds(seed=3)
    p = RouteParams()
    ok = np.ones_like(R.passable_mask(ds, p, None))
    cells, expanded, reach = R._astar(ok, ds.elev, ds.slope, 5.0, (0, 0), (59, 59),
                                      "terrain", p, budget=10)
    assert cells is None and reach is None and expanded == 10


def test_region_labels_match_reachability():
    """4-connected regions of the passable mask = cells A* (8-neighbour, no corner
    cutting) can reach."""
    ds = _rough_ds(seed=4)
    p = RouteParams()
    ok = R.passable_mask(ds, p, None)
    labels = R._components(ds, p, ok, cacheable=False)
    start = tuple(np.argwhere(ok)[0])
    _, _, reach = R._astar_py(ok, ds.elev, ds.slope, 5.0, start, (-1, -1), "shortest", p)
    reached = np.frombuffer(reach, dtype=np.uint8).reshape(ok.shape).astype(bool)
    assert np.array_equal(reached, labels == labels[start])


def test_disconnected_passable_points_report_no_route():
    ds, _ = _make_synthetic_ds(n=20, cell=5.0)
    ds.slope[:, 10] = 89.0  # wall
    with pytest.raises(RouteError) as exc:
        plan_route(ds, ds.grid.xy(10, 3), ds.grid.xy(10, 16), "shortest", RouteParams())
    assert exc.value.code == "no_feasible_route"


@pytest.mark.skipif(not (REAL / "analysis.npz").exists(), reason="real HiRISE grid not present")
def test_long_real_route_is_fast_and_near_optimal():
    """The full-study-area route that used to take minutes: under ~2 s per cost model
    (after warm-up) and within 2 % of the exact optimum."""
    from app.terrain import TerrainDataset
    R.warmup()
    ds = TerrainDataset(REAL)
    p = RouteParams()
    s = ds.proj.forward(137.36216, -4.47254)
    e = ds.proj.forward(137.52525, -4.68324)
    plan_route(ds, s, e, "shortest", p)  # build per-dataset caches, as the first request does
    ok = R.passable_mask(ds, p, None)
    for mode, key in (("shortest", "planimetric_length_m"), ("terrain", "modelled_terrain_cost")):
        t = time.perf_counter()
        fast = plan_route(ds, s, e, mode, p)
        assert time.perf_counter() - t < 2.0
        start, goal = tuple(fast["cell_path"][0]), tuple(fast["cell_path"][-1])
        exact, _, _ = R._astar(ok, ds.elev, ds.slope, ds.grid.cell, start, goal, mode, p)
        best = R.route_metrics(ds, exact, p, mode)[key]
        assert fast[key] <= best * 1.02
        assert fast["slope_max_deg"] <= p.max_slope_deg
