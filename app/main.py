"""COSMIC TRAIL — FastAPI backend.

All endpoints operate fully offline once the app is started.
No data is sent to any external server.
"""
from __future__ import annotations

import hashlib
import json
import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import (
    create_plan, delete_plan, export_briefing, export_geojson,
    get_plan, list_plans, update_plan,
)
from .geo import validate_lonlat
from .routing import RouteError, RouteParams, compare_routes, explain_tradeoff, plan_route
from .science import all_cards, card_by_id, mission_guide_query
from .terrain import TerrainDataset
from .assistant import Assistant
from .context import route_context
from .terrain_tiles import SIZE as TERRAIN_TILE_SIZE, TerrainContext, TerrainTiler, valid_tile
from .ortho_tiles import OrthoTiler

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "frontend" / "static"

# ---------------------------------------------------------------------------
# Dataset registry (loaded at startup)
# ---------------------------------------------------------------------------
DATASETS: dict[str, TerrainDataset] = {}
DATASET_PRIORITY = ["hirise_gale", "synthetic_demo"]
TERRAIN_CONTEXT_FILE = DATA_DIR / "terrain_context.npz"
TILERS: dict[str, TerrainTiler] = {}
TERRAIN_CONTEXT: TerrainContext | None = None
# HiRISE photo layer, per dataset: tiler over <dataset>/<ortho.mosaic> + its source images.
ORTHO: dict[str, OrthoTiler] = {}
ORTHO_SOURCES: dict[str, list[str]] = {}
ORTHO_NOTES: dict[str, str] = {}
MINERALS_FILE = DATA_DIR / "minerals" / "aqueous_minerals.json"
GEOLOGY_FILE = DATA_DIR / "usgs_geologic_units.geojson"
CURIOSITY_ROUTE_FILE = DATA_DIR / "curiosity_official_route.geojson"


def _load_datasets():
    for ds_id in DATASET_PRIORITY:
        folder = DATA_DIR / ds_id
        if folder.exists() and (folder / "metadata.json").exists():
            try:
                ds = TerrainDataset(folder)
                DATASETS[ds_id] = ds
                print(f"[COSMIC TRAIL] Loaded dataset: {ds_id} (kind={ds.kind})")
            except Exception as exc:
                print(f"[COSMIC TRAIL] Failed to load {ds_id}: {exc}")
    # 3D globe heights: MOLA context (optional) + each dataset's analysis grid.
    global TERRAIN_CONTEXT
    context = None
    if TERRAIN_CONTEXT_FILE.exists():
        try:
            context = TerrainContext(TERRAIN_CONTEXT_FILE)
            TERRAIN_CONTEXT = context
        except Exception as exc:
            print(f"[COSMIC TRAIL] Terrain context not loaded: {exc}")
    for ds_id, ds in DATASETS.items():
        if ds.proj is not None:
            TILERS[ds_id] = TerrainTiler(ds, context)
    # Optional HiRISE photo layer: the clipped ortho mosaic built by
    # scripts/build_ortho_mosaic.py (metadata.json "ortho.mosaic"), tiled on demand.
    for ds_id, ds in DATASETS.items():
        o = ds.meta.get("ortho") or {}
        if not o.get("mosaic"):
            continue
        path = ds.folder / o["mosaic"]
        if not path.exists():
            ORTHO_NOTES[ds_id] = (f"{o['mosaic']} not found in {ds_id}/ — run "
                                  "scripts/build_ortho_mosaic.py.")
            continue
        try:
            ORTHO[ds_id] = OrthoTiler(path, credit=o.get("credit") or "NASA/JPL-Caltech/UArizona")
            ORTHO_SOURCES[ds_id] = list(o.get("sources") or [])
        except Exception as exc:
            ORTHO_NOTES[ds_id] = f"Ortho mosaic not loaded: {exc}"
            print(f"[COSMIC TRAIL] Ortho mosaic for {ds_id} not loaded: {exc}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(application: FastAPI):
    _load_datasets()
    if not DATASETS:
        print("[COSMIC TRAIL] No datasets found. Run scripts/make_synthetic_demo.py first.")
    yield


app = FastAPI(
    title="COSMIC TRAIL",
    description="Offline Martian terrain route planner — NASA Space Apps 2026",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    # The Vite dev server is another origin: let it read download filenames.
    expose_headers=["Content-Disposition"],
)


# ---------------------------------------------------------------------------
# Static files & SPA
# ---------------------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    idx = ROOT / "frontend" / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return PlainTextResponse("COSMIC TRAIL backend running. Frontend not found.", status_code=200)


# ---------------------------------------------------------------------------
# Dataset endpoints
# ---------------------------------------------------------------------------
FILL_SOURCE_LABELS = {
    "usgs": "USGS Gale DEM fill",
    "mola": "MOLA 463 m gap fill",
}


@app.get("/api/datasets")
def api_datasets():
    out = []
    for ds_id, ds in DATASETS.items():
        is_synthetic = ds.kind == "synthetic_demo"
        out.append({
            "id": ds_id,
            "kind": ds.kind,
            "dataset_id": ds.dataset_id,
            "terrain_available": ds.terrain_available,
            "is_synthetic": is_synthetic,
            "synthetic_warning": (
                "⚠ SYNTHETIC DATA — not real terrain. "
                "For demonstration only. Run scripts/prepare_data.py for real NASA data."
            ) if is_synthetic else None,
            "coverage_fraction": ds.coverage_fraction() if ds.terrain_available else 0.0,
            "stats": ds.stats() if ds.terrain_available else {},
            "grid": {
                "x_min": ds.grid.x_min, "y_max": ds.grid.y_max,
                "x_max": ds.grid.x_max, "y_min": ds.grid.y_min,
                "cell": ds.grid.cell, "width": ds.grid.width, "height": ds.grid.height,
            } if ds.terrain_available else None,
            "crs": ds.meta.get("crs"),
            "study_window": ds.meta.get("study_window"),
            # True when HiRISE gaps were filled and the hatched overlay PNG exists.
            "fill_overlay": (ds.folder / "fill_overlay.png").exists(),
            "fill_source": ds.meta.get("fill_source"),
            "fill_label": FILL_SOURCE_LABELS.get(ds.meta.get("fill_source"), "Gap fill"),
            "fill_fraction": (ds.meta.get("stats") or {}).get("filled_fraction", 0.0),
        })
    return {"datasets": out}


@app.get("/api/datasets/{ds_id}/metadata")
def api_dataset_metadata(ds_id: str):
    if ds_id not in DATASETS:
        raise HTTPException(404, f"Dataset '{ds_id}' not found.")
    return DATASETS[ds_id].meta


@app.get("/api/datasets/{ds_id}/provenance")
def api_provenance(ds_id: str):
    if ds_id not in DATASETS:
        raise HTTPException(404, f"Dataset '{ds_id}' not found.")
    ds = DATASETS[ds_id]
    prov = ds.meta.get("provenance", {})
    checksums = ds.meta.get("checksums", {})
    return {
        "dataset_id": ds.dataset_id,
        "kind": ds.kind,
        "is_synthetic": ds.kind == "synthetic_demo",
        "provenance": prov,
        "checksums": checksums,
        "checksum_note": checksums.get(
            "checksum_note",
            "SHA-256 confirms file integrity. It does NOT prove NASA provenance.",
        ),
        "products": ds.meta.get("products_attempted"),
    }


@app.get("/api/datasets/{ds_id}/integrity")
def api_integrity(ds_id: str):
    if ds_id not in DATASETS:
        raise HTTPException(404, f"Dataset '{ds_id}' not found.")
    ds = DATASETS[ds_id]
    folder = ds.folder
    results = {}
    for fname, expected_sha in (ds.meta.get("checksums") or {}).items():
        if not fname.endswith("_sha256") or fname == "checksum_note":
            continue
        file_key = fname.replace("_sha256", "").replace("_arr", "")
        fpath = folder / ds.meta.get("analysis", {}).get("file", "analysis.npz") \
            if "npz" in fname else folder / f"{file_key}.png"
        if fpath.exists():
            h = hashlib.sha256(fpath.read_bytes()).hexdigest()
            results[fname] = {"expected": expected_sha, "actual": h, "ok": h == expected_sha}
        else:
            results[fname] = {"expected": expected_sha, "actual": None, "ok": False, "error": "file not found"}
    return {
        "dataset_id": ds_id,
        "integrity_checks": results,
        "note": "SHA-256 confirms the processed files are intact. "
                "It does not prove the original source was produced by NASA.",
    }


# ---------------------------------------------------------------------------
# Layer tiles (PNG layer images)
# ---------------------------------------------------------------------------
@app.get("/api/datasets/{ds_id}/layers/{layer_name}")
def api_layer(ds_id: str, layer_name: str):
    if ds_id not in DATASETS:
        raise HTTPException(404, "Dataset not found.")
    allowed = {"elevation", "slope", "hillshade", "thumbnail", "fill_overlay"}
    if layer_name not in allowed:
        raise HTTPException(400, f"Unknown layer. Must be one of: {sorted(allowed)}")
    folder = DATASETS[ds_id].folder
    fpath = folder / f"{layer_name}.png"
    if not fpath.exists():
        raise HTTPException(404, f"Layer '{layer_name}' has not been generated for this dataset.")
    return FileResponse(str(fpath), media_type="image/png")


# ---------------------------------------------------------------------------
# 3D globe terrain (height tiles)
# ---------------------------------------------------------------------------
@app.get("/api/datasets/{ds_id}/terrain")
def api_terrain_info(ds_id: str):
    """Whether 3D height tiles are available and how they are built."""
    if ds_id not in DATASETS:
        raise HTTPException(404, "Dataset not found.")
    tiler = TILERS.get(ds_id)
    ds = DATASETS[ds_id]
    available = bool(tiler and tiler.available)
    ref = None
    if ds.terrain_available and ds.elev is not None:
        finite = ds.elev[np.isfinite(ds.elev)]
        ref = round(float(np.median(finite)), 1) if finite.size else None
    return {
        "available": available,
        "tile_size": TERRAIN_TILE_SIZE,
        "tiling": "geographic (2x1 tiles at level 0), heights float32 LE, row-major from NW, metres",
        "reference_height_m": ref,
        "sources": [
            "Analysis grid (HiRISE DTMs + USGS gap fill, 5 m) inside the routing area",
            tiler.context.source if available else None,
        ] if available else [],
        "note": None if available else
            "Run scripts/build_terrain_context.py (needs the MOLA global DEM) to enable 3D terrain.",
    }


@app.get("/api/datasets/{ds_id}/terrain/{z}/{x}/{y}")
def api_terrain_tile(ds_id: str, z: int, x: int, y: int):
    tiler = TILERS.get(ds_id)
    if ds_id not in DATASETS or tiler is None or not tiler.available:
        raise HTTPException(404, "3D terrain not available for this dataset.")
    if not valid_tile(z, x, y):
        raise HTTPException(400, "Tile out of range for the geographic tiling scheme.")
    return Response(tiler.tile(z, x, y), media_type="application/octet-stream",
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# HiRISE orthoimage (imagery tiles)
# ---------------------------------------------------------------------------
@app.get("/api/datasets/{ds_id}/ortho")
def api_ortho_info(ds_id: str):
    """Footprint, zoom range, source images and credit of the dataset's HiRISE photo mosaic."""
    if ds_id not in DATASETS:
        raise HTTPException(404, "Dataset not found.")
    tiler = ORTHO.get(ds_id)
    if tiler is None:
        return {"available": False,
                "note": ORTHO_NOTES.get(ds_id, "This dataset has no HiRISE orthoimage.")}
    st = tiler.path.stat()
    return {**tiler.info(),
            # Changes whenever the mosaic is rebuilt; the client puts it in tile URLs so
            # browsers never show tiles cached from an older mosaic (tiles cache for a day).
            "version": f"{st.st_size:x}-{int(st.st_mtime):x}",
            "sources": ORTHO_SOURCES.get(ds_id, []),
            "tiling": "geographic (2x1 tiles at level 0), 256 px greyscale+alpha PNG"}


@app.get("/api/datasets/{ds_id}/ortho/{z}/{x}/{y}.png")
def api_ortho_tile(ds_id: str, z: int, x: int, y: int):
    tiler = ORTHO.get(ds_id)
    if ds_id not in DATASETS or tiler is None:
        raise HTTPException(404, "No orthoimage for this dataset.")
    if not valid_tile(z, x, y):
        raise HTTPException(400, "Tile out of range for the geographic tiling scheme.")
    return Response(tiler.tile(z, x, y), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# Terrain lookup
# ---------------------------------------------------------------------------
@app.get("/api/datasets/{ds_id}/lookup")
def api_lookup(ds_id: str, lon: float = Query(...), lat: float = Query(...)):
    if ds_id not in DATASETS:
        raise HTTPException(404, "Dataset not found.")
    try:
        validate_lonlat(lon, lat)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    ds = DATASETS[ds_id]
    if not ds.proj:
        raise HTTPException(400, "This dataset has no planetary CRS (synthetic without projection).")
    x, y = ds.proj.forward(lon, lat)
    out = ds.lookup(x, y)
    # Outside the analysis grid (or in a hole), report the coarse MOLA height used by the
    # 3D globe, clearly labelled — never as elevation_m, which is routing-grade data only.
    if out.get("elevation_m") is None and TERRAIN_CONTEXT is not None:
        h = float(TERRAIN_CONTEXT.sample(np.array([lon]), np.array([lat]))[0])
        if math.isfinite(h):
            out["context_elevation_m"] = round(h, 1)
            out["context_source"] = TERRAIN_CONTEXT.source
    return out


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
class PointIn(BaseModel):
    lon: float
    lat: float


class RouteRequest(BaseModel):
    dataset_id: str
    start: PointIn
    destination: PointIn
    mode: str = Field("both", description="'shortest', 'terrain', or 'both'")
    params: dict | None = None
    exclusion_zones: list[list[list[float]]] | None = Field(
        None, description="List of [x, y] polygon rings in local eqc metres"
    )


@app.post("/api/route")
def api_route(req: RouteRequest):
    ds_id = req.dataset_id
    if ds_id not in DATASETS:
        raise HTTPException(404, f"Dataset '{ds_id}' not found.")
    ds = DATASETS[ds_id]

    if not ds.proj:
        raise HTTPException(400, "This dataset has no projection (synthetic_demo with no CRS).")

    for label, pt in [("start", req.start), ("destination", req.destination)]:
        try:
            validate_lonlat(pt.lon, pt.lat)
        except ValueError as exc:
            raise HTTPException(400, f"Invalid {label}: {exc}")

    p = RouteParams.from_dict(req.params)

    # Rasterize exclusion zones
    exc_mask = None
    if req.exclusion_zones:
        from .routing import rasterize_polygons
        try:
            exc_mask = rasterize_polygons(ds, req.exclusion_zones)
        except RouteError as exc_err:
            raise HTTPException(400, exc_err.to_dict())

    start_xy = ds.proj.forward(req.start.lon, req.start.lat)
    end_xy = ds.proj.forward(req.destination.lon, req.destination.lat)

    modes = ["shortest", "terrain"] if req.mode == "both" else [req.mode]
    results = {}
    for m in modes:
        try:
            results[m] = plan_route(ds, start_xy, end_xy, m, p, exclusion=exc_mask)
        except RouteError as exc_err:
            raise HTTPException(422, exc_err.to_dict())
        # Science / thermal (dunes) / data-quality notes for the route panel (app/context.py).
        results[m]["context"] = route_context(ds, results[m], _minerals_data())

    response: dict[str, Any] = {
        "dataset_id": ds_id,
        "mode_requested": req.mode,
        "routes": results,
        "params_used": {
            "max_slope_deg": p.max_slope_deg,
            "caution_slope_deg": p.caution_slope_deg,
            "slope_weight": p.slope_weight,
            "climb_weight_per_m": p.climb_weight_per_m,
            "descent_weight_per_m": p.descent_weight_per_m,
            "params_note": "Slope thresholds based on Apollo EVA traverses (EPSC2024) and NASA MSL Engineering User Guide slope classifications.",
        },
    }

    if req.mode == "both" and "shortest" in results and "terrain" in results:
        cmp = compare_routes(results["shortest"], results["terrain"], ds.grid.cell)
        response["comparison"] = cmp
        response["tradeoff_summary"] = explain_tradeoff(results["shortest"], results["terrain"])
        if cmp["relation"] in ("identical", "equivalent"):
            response["note"] = cmp["text"]

    if ds.kind == "synthetic_demo":
        response["synthetic_warning"] = (
            "⚠ RESULTS COMPUTED ON SYNTHETIC TERRAIN — not real Mars data. "
            "These routes have no scientific or operational value."
        )
    return response


# ---------------------------------------------------------------------------
# Route export (the route on screen, without saving a plan)
# ---------------------------------------------------------------------------
class RouteExport(BaseModel):
    dataset_id: str
    start: PointIn
    destination: PointIn
    routes: dict = Field(..., description="RouteResponse.routes: {'terrain': {...}, 'shortest': {...}}")
    active_mode: str | None = Field(None, description="Route selected in the UI, listed first")
    params_used: dict | None = None
    tradeoff_summary: str | None = None
    name: str | None = None


@app.post("/api/route/export/{fmt}")
def api_route_export(fmt: str, body: RouteExport):
    """Download a computed route as GeoJSON (lon, lat, elevation) or a plain-text briefing."""
    if fmt not in ("geojson", "briefing"):
        raise HTTPException(400, "Format must be 'geojson' or 'briefing'.")
    if body.dataset_id not in DATASETS:
        raise HTTPException(404, "Dataset not found.")
    routes = {m: r for m, r in body.routes.items() if m in ("terrain", "shortest") and isinstance(r, dict)}
    if not any(r.get("lonlat") for r in routes.values()):
        raise HTTPException(400, "No route to export.")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    plan = {
        "id": None,
        "name": body.name or "Route export",
        "dataset_id": body.dataset_id,
        "created_at": now.isoformat(timespec="seconds"),
        "start_lon": body.start.lon, "start_lat": body.start.lat,
        "end_lon": body.destination.lon, "end_lat": body.destination.lat,
        "active_mode": body.active_mode,
        "route_data": {**routes, "params_used": body.params_used,
                       "tradeoff_summary": body.tradeoff_summary},
    }
    stamp = now.strftime("%Y%m%d-%H%M")
    if fmt == "geojson":
        return JSONResponse(content=export_geojson(plan), media_type="application/geo+json",
                            headers={"Content-Disposition": f'attachment; filename="cosmic_trail_route_{stamp}.geojson"'})
    text = export_briefing(plan, DATASETS[body.dataset_id].meta)
    return PlainTextResponse(content=text, media_type="text/plain; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="cosmic_trail_briefing_{stamp}.txt"'})


# ---------------------------------------------------------------------------
# Minerals layer (static, bundled by scripts/build_mineral_points.py)
# ---------------------------------------------------------------------------
@app.get("/api/layers/minerals")
def api_minerals():
    """Global aqueous-mineral detection points (Ehlmann & Edwards 2014; CRISM/OMEGA/THEMIS).

    Each point: c = class, lon/lat (planetocentric, east-positive), h = MOLA height (m,
    areoid) at that spot when the terrain context is built, so the 3D globe can place it.
    """
    if not MINERALS_FILE.exists():
        return {"available": False,
                "note": "Run scripts/build_mineral_points.py to download the mineral detection points."}
    data = json.loads(MINERALS_FILE.read_text(encoding="utf-8"))
    pts = data.get("points", [])
    if TERRAIN_CONTEXT is not None and pts:
        lon = np.array([p["lon"] for p in pts], dtype=np.float64)
        lat = np.array([p["lat"] for p in pts], dtype=np.float64)
        h = TERRAIN_CONTEXT.sample(lon, lat)
        for p, v in zip(pts, h):
            p["h"] = round(float(v), 1)
    return {"available": True, "type": "points", **data}


# ---------------------------------------------------------------------------
# NASA Space Apps reference layers (static GeoJSON bundled in data/)
# ---------------------------------------------------------------------------
def _geojson_file(path: Path, missing: str) -> JSONResponse:
    if not path.exists():
        raise HTTPException(404, missing)
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")),
                        media_type="application/geo+json")


@app.get("/api/geology/units")
def api_geology_units():
    """USGS geologic map units for the Gale study area (Tanaka et al. 2014, USGS SIM 3292)."""
    return _geojson_file(GEOLOGY_FILE, "Geologic units file data/usgs_geologic_units.geojson not found.")


@app.get("/api/curiosity/route")
def api_curiosity_route():
    """NASA's proposed Curiosity path up Mount Sharp, as a reference overlay."""
    return _geojson_file(CURIOSITY_ROUTE_FILE, "Route file data/curiosity_official_route.geojson not found.")


# ---------------------------------------------------------------------------
# ARIA assistant (rule-based, offline — app/assistant.py)
# ---------------------------------------------------------------------------
class AssistantContext(BaseModel):
    current_lon: float | None = None
    current_lat: float | None = None
    last_route: dict | None = None
    dataset_id: str | None = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)
    topic: str | None = None      # ARIA's fine-grained topic for its answers (follow-ups use it)


class AssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    context: AssistantContext = Field(default_factory=AssistantContext)
    # The last few messages of this browser tab's conversation, oldest first (optional; the server
    # stores nothing). Lets ARIA resolve follow-ups like "and at night?" or "what about south?".
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


_MINERALS_CACHE: dict | None = None


def _minerals_data() -> dict | None:
    global _MINERALS_CACHE
    if _MINERALS_CACHE is None and MINERALS_FILE.exists():
        _MINERALS_CACHE = json.loads(MINERALS_FILE.read_text(encoding="utf-8"))
    return _MINERALS_CACHE


@app.post("/api/assistant/chat")
def api_assistant_chat(req: AssistantRequest):
    ctx = req.context
    ds_id = ctx.dataset_id or next(
        (k for k, d in DATASETS.items() if d.proj is not None and d.terrain_available and d.kind != "synthetic_demo"),
        next((k for k, d in DATASETS.items() if d.proj is not None and d.terrain_available), None))
    if not ds_id or ds_id not in DATASETS:
        raise HTTPException(404, "No dataset with terrain is loaded.")
    ds = DATASETS[ds_id]
    if ds.proj is None or not ds.terrain_available:
        raise HTTPException(400, "This dataset has no terrain grid with a planetary CRS.")
    # Default position: Bradbury Landing (published 4.5895 S, 137.4417 E).
    lon = ctx.current_lon if ctx.current_lon is not None else 137.4417
    lat = ctx.current_lat if ctx.current_lat is not None else -4.5895
    try:
        validate_lonlat(lon, lat)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid position: {exc}")
    previous = None
    last_aria = next((i for i in range(len(req.history) - 1, -1, -1)
                      if req.history[i].role == "assistant" and req.history[i].topic), None)
    if last_aria is not None:
        asked = next((t.content for t in reversed(req.history[:last_aria]) if t.role == "user"), "")
        previous = {"topic": req.history[last_aria].topic, "message": asked}
    out = Assistant(ds, TERRAIN_CONTEXT, _minerals_data()).answer(req.message, lon, lat, ctx.last_route, previous)
    out["dataset_id"] = ds_id
    if ds.kind == "synthetic_demo":
        out["reply"] = "⚠ SYNTHETIC TERRAIN — not real Mars data. " + out["reply"]
        out["confidence"] = "none"
    return out


# ---------------------------------------------------------------------------
# Science cards
# ---------------------------------------------------------------------------
@app.get("/api/science/cards")
def api_science_cards():
    return {"cards": all_cards()}


@app.get("/api/science/cards/{card_id}")
def api_science_card(card_id: str):
    card = card_by_id(card_id)
    if card is None:
        raise HTTPException(404, f"Card '{card_id}' not found.")
    return card


# ---------------------------------------------------------------------------
# Mission Guide
# ---------------------------------------------------------------------------
class GuideQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


@app.post("/api/guide/query")
def api_guide_query(body: GuideQuery):
    return mission_guide_query(body.query)


# ---------------------------------------------------------------------------
# Plan CRUD
# ---------------------------------------------------------------------------
class PlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    dataset_id: str
    start_lon: float | None = None
    start_lat: float | None = None
    end_lon: float | None = None
    end_lat: float | None = None
    route_mode: str | None = None
    route_data: dict | None = None
    params: dict | None = None
    notes: str | None = None


class PlanUpdate(BaseModel):
    name: str | None = None
    start_lon: float | None = None
    start_lat: float | None = None
    end_lon: float | None = None
    end_lat: float | None = None
    route_mode: str | None = None
    route_data: dict | None = None
    params: dict | None = None
    notes: str | None = None


@app.get("/api/plans")
def api_list_plans():
    return {"plans": list_plans()}


@app.post("/api/plans", status_code=201)
def api_create_plan(body: PlanCreate):
    return create_plan(**body.model_dump())


@app.get("/api/plans/{plan_id}")
def api_get_plan(plan_id: str):
    p = get_plan(plan_id)
    if not p:
        raise HTTPException(404, "Plan not found.")
    return p


@app.patch("/api/plans/{plan_id}")
def api_update_plan(plan_id: str, body: PlanUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    p = update_plan(plan_id, **updates)
    if not p:
        raise HTTPException(404, "Plan not found.")
    return p


@app.delete("/api/plans/{plan_id}", status_code=204)
def api_delete_plan(plan_id: str):
    if not delete_plan(plan_id):
        raise HTTPException(404, "Plan not found.")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
@app.get("/api/plans/{plan_id}/export/geojson")
def api_export_geojson(plan_id: str):
    p = get_plan(plan_id)
    if not p:
        raise HTTPException(404, "Plan not found.")
    ds_meta = DATASETS[p["dataset_id"]].meta if p.get("dataset_id") in DATASETS else None
    gj = export_geojson(p)
    return JSONResponse(content=gj, media_type="application/geo+json",
                        headers={"Content-Disposition": f'attachment; filename="plan_{plan_id[:8]}.geojson"'})


@app.get("/api/plans/{plan_id}/export/json")
def api_export_json(plan_id: str):
    p = get_plan(plan_id)
    if not p:
        raise HTTPException(404, "Plan not found.")
    return JSONResponse(content=p, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="plan_{plan_id[:8]}.json"'})


@app.get("/api/plans/{plan_id}/export/briefing")
def api_export_briefing(plan_id: str):
    p = get_plan(plan_id)
    if not p:
        raise HTTPException(404, "Plan not found.")
    ds_meta = DATASETS[p["dataset_id"]].meta if p.get("dataset_id") in DATASETS else None
    text = export_briefing(p, ds_meta)
    return PlainTextResponse(content=text,
                             headers={"Content-Disposition": f'attachment; filename="briefing_{plan_id[:8]}.txt"'})


# ---------------------------------------------------------------------------
# Health / info
# ---------------------------------------------------------------------------
@app.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "datasets_loaded": list(DATASETS.keys()),
        "offline_capable": True,
        "note": "COSMIC TRAIL runs fully offline. No data leaves this machine.",
    }
