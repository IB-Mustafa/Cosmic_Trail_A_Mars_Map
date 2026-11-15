"""End-to-end API tests for COSMIC TRAIL.

Uses httpx.AsyncClient in ASGI transport mode — no network connection needed.
Run:  pytest tests/test_api.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module")
async def client():
    from app.main import app, _load_datasets, DATASETS
    # ASGITransport does not fire lifespan events; load datasets explicitly.
    if not DATASETS:
        _load_datasets()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ---- health ----

async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["offline_capable"] is True


# ---- datasets ----

async def test_datasets_list(client):
    r = await client.get("/api/datasets")
    assert r.status_code == 200
    d = r.json()
    assert "datasets" in d
    ids = [ds["id"] for ds in d["datasets"]]
    assert "synthetic_demo" in ids


async def test_dataset_metadata(client):
    r = await client.get("/api/datasets/synthetic_demo/metadata")
    assert r.status_code == 200
    d = r.json()
    assert d["kind"] == "synthetic_demo"
    assert "DISCLAIMER" in d


async def test_dataset_provenance(client):
    r = await client.get("/api/datasets/synthetic_demo/provenance")
    assert r.status_code == 200
    d = r.json()
    assert d["is_synthetic"] is True
    assert "checksum_note" in d


async def test_dataset_integrity(client):
    r = await client.get("/api/datasets/synthetic_demo/integrity")
    assert r.status_code == 200
    d = r.json()
    assert "integrity_checks" in d


async def test_dataset_not_found(client):
    r = await client.get("/api/datasets/does_not_exist/metadata")
    assert r.status_code == 404


# ---- layers ----

async def test_layer_hillshade(client):
    r = await client.get("/api/datasets/synthetic_demo/layers/hillshade")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 1000


async def test_layer_elevation(client):
    r = await client.get("/api/datasets/synthetic_demo/layers/elevation")
    assert r.status_code == 200


async def test_layer_slope(client):
    r = await client.get("/api/datasets/synthetic_demo/layers/slope")
    assert r.status_code == 200


async def test_layer_unknown(client):
    r = await client.get("/api/datasets/synthetic_demo/layers/fake")
    assert r.status_code == 400


# ---- lookup ----

async def test_lookup_centre(client):
    r = await client.get(
        "/api/datasets/synthetic_demo/lookup",
        params={"lon": 137.4417, "lat": -4.5895},
    )
    assert r.status_code == 200
    d = r.json()
    assert "elevation_m" in d
    assert "slope_deg" in d


async def test_lookup_outside(client):
    r = await client.get(
        "/api/datasets/synthetic_demo/lookup",
        params={"lon": 0.0, "lat": 0.0},
    )
    assert r.status_code == 200
    d = r.json()
    # Outside grid: either 'outside' key or 'in_study_area: False'
    assert d.get("outside") is True or d.get("in_study_area") is False


# ---- routing ----
# Route tests run on the real NASA HiRISE DTMs of Gale Crater
# (DTEEC_023957_1755_024023_1755_U01 + DTEEC_009505_1755_009571_1755_U01,
# merged by scripts/prepare_data.py) with the default RouteParams,
# not on synthetic terrain or loosened slope limits.

REAL_DS = "hirise_gale"
REAL_START = {"lon": 137.45, "lat": -4.60}
REAL_DEST = {"lon": 137.47, "lat": -4.58}


async def _require_real_dataset(client):
    r = await client.get("/api/datasets")
    if REAL_DS not in [d["id"] for d in r.json()["datasets"]]:
        pytest.skip(f"{REAL_DS} dataset not present in data/")


async def test_route_shortest(client):
    await _require_real_dataset(client)
    r = await client.post("/api/route", json={
        "dataset_id": REAL_DS,
        "start": REAL_START,
        "destination": REAL_DEST,
        "mode": "shortest",
    })
    assert r.status_code == 200
    d = r.json()
    assert "routes" in d
    assert "shortest" in d["routes"]
    route = d["routes"]["shortest"]
    assert route["cells"] > 0
    assert route["planimetric_length_m"] > 0
    assert len(route["xy"]) == route["cells"]
    assert d["params_used"]["max_slope_deg"] == 15.0
    assert d.get("synthetic_warning") is None


async def test_route_terrain(client):
    await _require_real_dataset(client)
    r = await client.post("/api/route", json={
        "dataset_id": REAL_DS,
        "start": REAL_START,
        "destination": REAL_DEST,
        "mode": "terrain",
    })
    assert r.status_code == 200
    d = r.json()
    assert "terrain" in d["routes"]


async def test_route_both(client):
    await _require_real_dataset(client)
    r = await client.post("/api/route", json={
        "dataset_id": REAL_DS,
        "start": REAL_START,
        "destination": REAL_DEST,
        "mode": "both",
    })
    assert r.status_code == 200
    d = r.json()
    assert "shortest" in d["routes"]
    assert "terrain" in d["routes"]
    assert "comparison" in d
    assert d["comparison"]["relation"] in ("identical", "equivalent", "different")


async def test_usgs_gap_fill_route_and_connected_endpoint_snapping(client):
    """Keep passable USGS terrain routable and snap steep endpoints into A's component."""
    import numpy as np

    await _require_real_dataset(client)
    start = {"lat": -4.70909, "lon": 137.45159}
    destinations = [
        {"lat": -4.70909, "lon": 137.48544},
        {"lat": -4.70889, "lon": 137.48544},
    ]
    analysis = Path(__file__).resolve().parents[1] / "data" / REAL_DS / "analysis.npz"
    if not analysis.exists():
        pytest.skip("real HiRISE analysis grid is not present")

    for destination in destinations:
        mode = "both" if destination["lat"] == -4.70889 else "shortest"
        response = await client.post("/api/route", json={
            "dataset_id": REAL_DS, "start": start, "destination": destination, "mode": mode,
        })
        assert response.status_code == 200, response.text
        routes = response.json()["routes"].values()
        with np.load(analysis) as data:
            for route in routes:
                cells = np.asarray(route["cell_path"], dtype=int)
                assert data["usgs_filled"][cells[:, 0], cells[:, 1]].all()
                assert route["slope_max_deg"] <= 15.0
                if destination["lat"] == -4.70889:
                    assert cells[-1].tolist() == [3070, 1600]


async def test_passable_disconnected_endpoint_suggests_without_moving(client):
    """An isolated but passable point stays fixed and gets a reachable-point suggestion."""
    await _require_real_dataset(client)
    start = {"lat": -4.70909, "lon": 137.45159}
    destination = {"lat": -4.70879, "lon": 137.48544}
    response = await client.post("/api/route", json={
        "dataset_id": REAL_DS, "start": start, "destination": destination, "mode": "shortest",
    })
    assert response.status_code == 422
    error = response.json()["detail"]
    assert error["error"] == "no_feasible_route"
    assert "was not moved" in error["message"]
    suggestion = error["details"]["suggested_destination"]
    assert suggestion["lat"] != destination["lat"] or suggestion["lon"] != destination["lon"]

    confirmed = await client.post("/api/route", json={
        "dataset_id": REAL_DS,
        "start": start,
        "destination": {"lat": suggestion["lat"], "lon": suggestion["lon"]},
        "mode": "shortest",
    })
    assert confirmed.status_code == 200, confirmed.text


async def test_route_params_propagated(client):
    # A non-default max_slope_deg must be echoed back in params_used.
    await _require_real_dataset(client)
    r = await client.post("/api/route", json={
        "dataset_id": REAL_DS,
        "start": REAL_START,
        "destination": REAL_DEST,
        "mode": "shortest",
        "params": {"max_slope_deg": 25},
    })
    assert r.status_code == 200
    d = r.json()
    assert d["params_used"]["max_slope_deg"] == 25
    note = d["params_used"]["params_note"]
    assert "Apollo EVA traverses (EPSC2024)" in note
    assert "NASA MSL Engineering User Guide" in note


async def test_fill_overlay_layer(client):
    """The gap-fill overlay (USGS Gale DEM or MOLA) is listed and served for the real dataset."""
    await _require_real_dataset(client)
    r = await client.get("/api/datasets")
    ds = next(d for d in r.json()["datasets"] if d["id"] == REAL_DS)
    if not ds["fill_overlay"]:
        pytest.skip("dataset was built without gap fill")
    assert ds["fill_source"] in ("usgs", "mola")
    assert 0 < ds["fill_fraction"] < 1
    r = await client.get(f"/api/datasets/{REAL_DS}/layers/fill_overlay")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


async def test_lookup_outside_grid_reports_mola_context(client):
    await _require_real_dataset(client)
    if not (await client.get(f"/api/datasets/{REAL_DS}/terrain")).json()["available"]:
        pytest.skip("terrain context not built")
    # Aeolis Mons summit area: well outside the 5 m analysis grid.
    d = (await client.get(f"/api/datasets/{REAL_DS}/lookup", params={"lon": 137.85, "lat": -5.08})).json()
    assert d["in_study_area"] is False and "elevation_m" not in d
    assert -6000 < d["context_elevation_m"] < 2000
    assert d["context_source"]
    # Inside the grid the routing-grade value is used and no context value is added.
    d = (await client.get(f"/api/datasets/{REAL_DS}/lookup", params=REAL_START)).json()
    assert d["elevation_m"] is not None and "context_elevation_m" not in d


async def test_lookup_reports_elevation_source(client):
    await _require_real_dataset(client)
    r = await client.get(f"/api/datasets/{REAL_DS}/lookup", params=REAL_START)
    assert r.status_code == 200
    assert r.json()["elevation_source"] in (
        "HiRISE", "USGS Gale DEM (gap fill)", "MOLA 463 m (gap fill)")


async def test_route_bad_dataset(client):
    r = await client.post("/api/route", json={
        "dataset_id": "nope",
        "start": {"lon": 137.4, "lat": -4.5},
        "destination": {"lon": 137.5, "lat": -4.4},
        "mode": "shortest",
    })
    assert r.status_code == 404


async def test_route_bad_coords(client):
    r = await client.post("/api/route", json={
        "dataset_id": "synthetic_demo",
        "start": {"lon": 999, "lat": 999},
        "destination": {"lon": 137.5, "lat": -4.4},
        "mode": "shortest",
    })
    assert r.status_code == 400


# ---- science ----

async def test_science_cards_list(client):
    r = await client.get("/api/science/cards")
    assert r.status_code == 200
    d = r.json()
    assert len(d["cards"]) >= 3


async def test_science_card_bradbury(client):
    r = await client.get("/api/science/cards/bradbury_landing")
    assert r.status_code == 200
    d = r.json()
    assert d["card_id"] == "bradbury_landing"
    assert d["lon"] is not None
    assert d["lat"] is not None
    assert len(d["sources"]) > 0
    assert len(d["caveats"]) > 0


async def test_science_card_not_found(client):
    r = await client.get("/api/science/cards/fake_site")
    assert r.status_code == 404


# ---- guide ----

async def test_guide_matched(client):
    r = await client.post("/api/guide/query", json={"query": "water evidence clay"})
    assert r.status_code == 200
    d = r.json()
    assert "response" in d
    assert "disclaimer" in d
    # Disclaimer must say it is not AI
    disc = d["disclaimer"].lower()
    assert "not an ai" in disc or "rule-based" in disc


async def test_guide_unmatched(client):
    r = await client.post("/api/guide/query", json={"query": "xyzzy purple elephant"})
    assert r.status_code == 200
    d = r.json()
    assert "unmatched_note" in d


# ---- route export (the route on screen, no saved plan) ----

async def test_route_export_geojson_and_briefing(client):
    await _require_real_dataset(client)
    start, end = {"lon": 137.4417, "lat": -4.5895}, {"lon": 137.47, "lat": -4.58}
    r = (await client.post("/api/route", json={
        "dataset_id": REAL_DS, "start": start, "destination": end, "mode": "both",
    })).json()
    body = {"dataset_id": REAL_DS, "start": start, "destination": end, "routes": r["routes"],
            "active_mode": "terrain", "params_used": r["params_used"],
            "tradeoff_summary": r["tradeoff_summary"]}

    g = await client.post("/api/route/export/geojson", json=body)
    assert g.status_code == 200
    assert g.headers["content-disposition"].startswith("attachment;") and ".geojson" in g.headers["content-disposition"]
    gj = g.json()
    assert gj["type"] == "FeatureCollection" and "disclaimer" in gj["properties"]
    lines = [f for f in gj["features"] if f["geometry"]["type"] == "LineString"]
    assert lines[0]["properties"]["mode"] == "terrain"            # selected route first
    terrain = r["routes"]["terrain"]
    coords = lines[0]["geometry"]["coordinates"]
    assert len(coords) == len(terrain["lonlat"])
    assert all(len(c) == 3 for c in coords)                       # lon, lat, elevation
    assert coords[0][2] == round(terrain["elevation_profile"][0], 2)
    assert {f["properties"].get("label") for f in gj["features"]} >= {"start", "destination"}

    b = await client.post("/api/route/export/briefing", json=body)
    assert b.status_code == 200 and ".txt" in b.headers["content-disposition"]
    text = b.text
    for s in ("COSMIC TRAIL", "TERRAIN-SAFE ROUTE (SELECTED)", "SHORTEST ROUTE", "Elevation gain",
              "Slope (mean / max)", "Warnings", "DATA SOURCES", "HiRISE DTM", "prototype"):
        assert s in text, s

    assert (await client.post("/api/route/export/pdf", json=body)).status_code == 400
    empty = {**body, "routes": {}}
    assert (await client.post("/api/route/export/geojson", json=empty)).status_code == 400


# ---- plans ----

async def test_plan_crud(client):
    # Create
    r = await client.post("/api/plans", json={
        "name": "Test plan",
        "dataset_id": "synthetic_demo",
        "start_lon": 137.435, "start_lat": -4.595,
        "end_lon": 137.455, "end_lat": -4.570,
        "route_mode": "shortest",
        "route_data": {"shortest": {"cells": 5, "planimetric_length_m": 100}},
    })
    assert r.status_code == 201
    plan = r.json()
    plan_id = plan["id"]

    # Get
    r2 = await client.get(f"/api/plans/{plan_id}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Test plan"

    # List
    r3 = await client.get("/api/plans")
    ids = [p["id"] for p in r3.json()["plans"]]
    assert plan_id in ids

    # Update
    r4 = await client.patch(f"/api/plans/{plan_id}", json={"name": "Renamed"})
    assert r4.status_code == 200
    assert r4.json()["name"] == "Renamed"

    # GeoJSON export
    r5 = await client.get(f"/api/plans/{plan_id}/export/geojson")
    assert r5.status_code == 200
    gj = r5.json()
    assert gj["type"] == "FeatureCollection"
    assert "disclaimer" in gj["properties"]

    # Briefing export
    r6 = await client.get(f"/api/plans/{plan_id}/export/briefing")
    assert r6.status_code == 200
    text = r6.text
    assert "COSMIC TRAIL" in text
    assert "prototype" in text.lower()

    # Delete
    r7 = await client.delete(f"/api/plans/{plan_id}")
    assert r7.status_code == 204

    # Gone
    r8 = await client.get(f"/api/plans/{plan_id}")
    assert r8.status_code == 404


# ---- index / static ----

async def test_index_html(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert b"COSMIC TRAIL" in r.content


async def test_ol_js_served(client):
    r = await client.get("/static/ol/ol.js")
    assert r.status_code == 200
    assert len(r.content) > 100_000


# ---- 3D globe terrain tiles ----

async def test_terrain_info(client):
    await _require_real_dataset(client)
    r = await client.get(f"/api/datasets/{REAL_DS}/terrain")
    assert r.status_code == 200
    info = r.json()
    if not info["available"]:
        pytest.skip("data/terrain_context.npz not built (scripts/build_terrain_context.py)")
    assert info["tile_size"] == 65
    assert -6000 < info["reference_height_m"] < -3000


async def test_terrain_tile_heights(client):
    """A tile over Bradbury Landing returns 65x65 float32 heights matching the 5 m grid."""
    import math
    import numpy as np
    await _require_real_dataset(client)
    if not (await client.get(f"/api/datasets/{REAL_DS}/terrain")).json()["available"]:
        pytest.skip("terrain context not built")
    z, lon, lat = 14, 137.4417, -4.5895
    span = 180 / 2 ** z
    x, y = int((lon + 180) // span), int((90 - lat) // span)
    r = await client.get(f"/api/datasets/{REAL_DS}/terrain/{z}/{x}/{y}")
    assert r.status_code == 200
    a = np.frombuffer(r.content, "<f4").reshape(65, 65)
    assert np.isfinite(a).all()
    col = round((lon - (-180 + x * span)) / span * 64)
    row = round(((90 - y * span) - lat) / span * 64)
    look = (await client.get(f"/api/datasets/{REAL_DS}/lookup", params={"lon": lon, "lat": lat})).json()
    assert math.isclose(float(a[row, col]), look["elevation_m"], abs_tol=2.0)
    assert (await client.get(f"/api/datasets/{REAL_DS}/terrain/1/99/0")).status_code == 400



async def test_ortho_tiles(client):
    import io
    import math
    from PIL import Image
    await _require_real_dataset(client)
    info = (await client.get(f"/api/datasets/{REAL_DS}/ortho")).json()
    if not info["available"]:
        pytest.skip(info.get("note") or "orthoimage not available")
    # Clipped exactly to the study window (scripts/build_ortho_mosaic.py).
    for k, v in {"west": 137.35, "east": 137.55, "south": -4.75, "north": -4.45}.items():
        assert math.isclose(info[k], v, abs_tol=1e-9), k
    assert info["sources"] and info["version"]
    z = info["max_level"]
    span = 180 / 2 ** z
    lon, lat = 137.4417, -4.5895   # Bradbury Landing: inside ESP_018854
    x, y = int((lon + 180) // span), int((90 - lat) // span)
    r = await client.get(f"/api/datasets/{REAL_DS}/ortho/{z}/{x}/{y}.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (256, 256) and img.mode == "LA"
    assert img.getchannel("A").getextrema() == (255, 255)   # fully covered by the photos
    # Far from the footprint: a fully transparent tile, not an error.
    r = await client.get(f"/api/datasets/{REAL_DS}/ortho/{z}/0/0.png")
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).getchannel("A").getextrema() == (0, 0)
    assert (await client.get(f"/api/datasets/{REAL_DS}/ortho/1/99/0.png")).status_code == 400


# ---- minerals layer ----

async def test_minerals_layer(client):
    r = await client.get("/api/layers/minerals")
    assert r.status_code == 200
    d = r.json()
    if not d["available"]:
        pytest.skip("data/minerals/aqueous_minerals.json not built")
    assert d["type"] == "points"
    classes = {l["class"] for l in d["legend"]}
    assert {"phyllosilicate", "sulfate"} <= classes
    assert all(l["color"].startswith("#") for l in d["legend"])
    p = d["points"][0]
    assert -180 <= p["lon"] <= 180 and -90 <= p["lat"] <= 90 and p["c"] in classes
    assert "Ehlmann" in d["citation"]


# ---- NASA Space Apps official resources ----

async def test_curiosity_route_geojson(client):
    r = await client.get("/api/curiosity/route")
    assert r.status_code == 200
    d = r.json()
    assert d["type"] == "FeatureCollection"
    f = d["features"][0]
    assert f["geometry"]["type"] == "LineString"
    assert len(f["geometry"]["coordinates"]) == 6
    wps = f["properties"]["waypoints"]
    assert len(wps) == 6
    assert wps[0]["name"] == "Bradbury Landing"
    assert "science.nasa.gov" in f["properties"]["url"]
    for wp, (lon, lat) in zip(wps, f["geometry"]["coordinates"]):
        assert (wp["lon"], wp["lat"]) == (lon, lat)


async def test_geology_units_geojson(client):
    r = await client.get("/api/geology/units")
    assert r.status_code == 200
    d = r.json()
    assert d["type"] == "FeatureCollection"
    units = {f["properties"]["unit"]: f for f in d["features"]}
    assert set(units) == {"eHt", "Htu"}
    for f in units.values():
        assert f["geometry"]["type"] == "Polygon"
        ring = f["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]
        for lon, lat in ring:   # inside the study area
            assert 137.30 <= lon <= 137.60 and -4.85 <= lat <= -4.35
        assert "SIM 3292" in f["properties"]["source"]


async def test_guide_dust_returns_dust_storm_card(client):
    r = await client.post("/api/guide/query", json={"query": "Is dust a problem?"})
    assert r.status_code == 200
    ids = [c["card_id"] for c in r.json()["matched_cards"]]
    assert "dust_storms" in ids


async def test_guide_storm_weather_and_images(client):
    for q, card in [("storm risk", "dust_storms"), ("weather today", "dust_storms"),
                    ("show me a photo", "surface_imagery_context"),
                    ("rover camera", "surface_imagery_context"),
                    ("proposed path up Mount Sharp", "curiosity_official_route")]:
        r = await client.post("/api/guide/query", json={"query": q})
        ids = [c["card_id"] for c in r.json()["matched_cards"]]
        assert card in ids, q


async def test_new_science_cards_exist(client):
    for cid in ("curiosity_official_route", "dust_storms", "surface_imagery_context"):
        r = await client.get(f"/api/science/cards/{cid}")
        assert r.status_code == 200
        assert r.json()["sources"]
