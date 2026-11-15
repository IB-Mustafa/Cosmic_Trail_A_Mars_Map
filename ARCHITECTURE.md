# How COSMIC TRAIL is built

COSMIC TRAIL runs on one computer: a Python backend that holds the data and does the work, and a
web frontend that shows the globe. Apart from the NASA Mars Trek basemap tiles, nothing needs the
internet once the data is downloaded.

```
Browser: React + TypeScript + Vite (http://127.0.0.1:5173)
  ├─ CesiumJS globe (via Resium)    terrain, photo tiles, routes, labels
  ├─ Zustand stores                 layers, route, picked points
  ├─ Recharts elevation profile
  └─ ARIA chat panel
        │  HTTP / JSON (localhost)
        ▼
FastAPI backend (http://127.0.0.1:8000)
  ├─ TerrainDataset     data/hirise_gale/analysis.npz   (5 m elevation + slope grid)
  ├─ Router             numba-compiled A*, two cost models
  ├─ Tile servers       3D terrain tiles, HiRISE photo tiles
  ├─ ARIA               rule-based assistant (no language model)
  ├─ Reference layers   minerals, geology, Curiosity path, science cards
  └─ SQLite             data/plans.db (saved plans, API only)
```

## The data on disk

Everything lives in `data/`, which we download from Hugging Face with
`python scripts/download_data.py`. It isn't in Git.

| File | What it is |
|------|------------|
| `hirise_gale/analysis.npz` | The 5 m grid: elevation, Horn slope, and masks for USGS/MOLA-filled cells |
| `hirise_gale/metadata.json` | Source tiles, CRS, coverage stats, gap-fill details, checksums |
| `hirise_gale/ortho_mosaic.tif` | HiRISE photo mosaic, 1 m/px (optional `ortho_mosaic_50cm.tif`) |
| `hirise_gale/*.png` | Hillshade, elevation and slope overlays |
| `terrain_context.npz` | MOLA heights for the globe outside the study area |
| `minerals/aqueous_minerals.json` | 2,417 mineral detection sites |
| `usgs_geologic_units.geojson`, `curiosity_official_route.geojson`, `hazard_zones.geojson` | Reference overlays |
| `synthetic_demo/` | Generated test terrain, used by tests and as a fallback |

The study window is 137.35–137.55°E, 4.75–4.45°S, about 11.8 km × 17.8 km. The grid is
2,364 × 3,558 cells in a local equidistant cylindrical projection centred on 137.45°E, 4.6°S,
on the Mars sphere (R = 3,396,190 m), with planetocentric latitude and east-positive longitude.

## Backend (`app/`)

| Module | What it does |
|--------|--------------|
| `main.py` | FastAPI app: loads datasets at startup, defines every endpoint |
| `geo.py` | Mars sphere, local projection, great-circle distances |
| `terrain.py` | Loads the grid; lookups by position; Horn (1981) slope |
| `routing.py` | A* search, cost models, route metrics, route comparison |
| `terrain_tiles.py` | 65×65 height tiles for the 3D globe (5 m grid inside, MOLA outside, blended at the edge) |
| `ortho_tiles.py` | 256 px HiRISE photo tiles cut on demand from the mosaic, with an in-memory cache |
| `assistant.py`, `aria_nlu.py`, `aria_templates.py`, `aria_places.py` | ARIA: understanding, answers, wording, place names |
| `context.py` | Point context: geologic unit, nearest minerals and clays, dunes, data source |
| `weather_facts.py` | Published temperature and radiation figures, each with its citation |
| `science.py` | Science cards with references, and the older keyword Mission Guide |
| `db.py` | SQLite plans and exports |

### Routing

The grid is 8-connected and diagonal moves can't cut corners. Cells steeper than the 15° limit,
or without slope, are blocked. We run two cost models:

- **shortest**: cost = step length;
- **terrain**: cost = step length × (1 + 4 × (slope / 15°)²) + 2 × metres climbed + 0.5 × metres
  descended.

The heuristic is the octile distance, plus the net climb or descent cost to the goal in terrain
mode. It never overestimates, so routes are optimal for their cost model.

To make long routes fast, we did four things:

1. The search is compiled with numba. A pure-Python version stays as a fallback and as the
   reference in tests.
2. Walkable regions are labelled once, so a blocked endpoint snaps into reachable ground straight
   away.
3. Routes longer than 3 km first try the exact search with a budget. If that runs out, we route on
   a coarse 20 m grid, then search again at 5 m inside a corridor around it. Each response says
   whether the route came from the `exact` or the `corridor` search.
4. Both cost models run in parallel.

Two routes count as "equivalent" when they're within 2 cells (Hausdorff distance) and their
lengths differ by less than 1%.

### Main endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health`, `GET /api/datasets`, `GET /api/datasets/{id}/metadata` | Status, datasets, full metadata |
| `GET /api/datasets/{id}/provenance`, `/integrity` | Source files and checksum checks |
| `GET /api/datasets/{id}/layers/{name}` | Hillshade, elevation or slope PNG |
| `GET /api/datasets/{id}/terrain`, `/terrain/{z}/{x}/{y}` | 3D terrain info and height tiles |
| `GET /api/datasets/{id}/ortho`, `/ortho/{z}/{x}/{y}.png` | HiRISE photo info and tiles |
| `GET /api/datasets/{id}/lookup` | Elevation, slope and source at a point |
| `POST /api/route`, `POST /api/route/export/{fmt}` | Plan both routes; export as GeoJSON or a text briefing |
| `GET /api/layers/minerals`, `/api/geology/units`, `/api/curiosity/route` | Reference layers |
| `POST /api/assistant/chat` | Ask ARIA |
| `GET /api/science/cards`, `POST /api/guide/query` | Science cards and the old Mission Guide |
| `/api/plans/...` | Save, list, update, delete and export plans (not used by the current UI) |

CORS is open (`*`) because this only runs locally.

### ARIA

ARIA doesn't use a language model. A question goes through three steps:

1. **Understand** (`aria_nlu.py`): clean the text, expand short forms, fix typos against ARIA's
   own vocabulary, then find topics (slope, temperature, route...), modifiers (day or night,
   compass direction, comparison, "why") and place names. The chat sends the last few messages, so
   follow-ups like "and at night?" use the previous topic.
2. **Compute** (`assistant.py`): read the answer from our data. Slope at a point or in a 500 m
   compass sector comes from the 5 m grid, route checks from the last route, minerals and
   geology from the reference layers, and temperatures from `weather_facts.py`.
3. **Word** (`aria_templates.py`): a direct answer, the reason with the real numbers, a tip,
   then a `Source:` line. Replies that used no data, like a greeting or "I didn't understand",
   carry no source.

## Frontend (`frontend/src/`)

| File | What it does |
|------|--------------|
| `App.tsx`, `App.css` | Layout: full-screen globe with glass panels on top |
| `components/Globe.tsx` | Cesium viewer: terrain, basemaps, photo layer, routes, markers, info cards |
| `components/MarsLabels.ts`, `labelStyle.ts` | One label style, and the declutter that keeps labels from overlapping |
| `components/MineralPoints.ts` | Mineral detection points |
| `components/ZoomAids.tsx` | HiRISE zoom stop, "max detail" chip, scale bar |
| `components/RoutePanel.tsx` | Start and destination, picking, route results |
| `components/ElevationChart.tsx`, `ResizablePanel.tsx` | Resizable elevation profile and exports |
| `components/Inspector.tsx` | Hover bar: position, elevation, slope, data source |
| `components/LayerControls.tsx` | Layer toggles |
| `components/Chatbot.tsx` | ARIA chat panel |
| `store/*.ts` | Zustand stores |
| `api/cosmic.ts` | Every backend call |
| `mapFrame.ts`, `mars.ts` | Centring views on the uncovered map area; the Mars sphere and place names |

The old OpenLayers page is kept in `frontend/legacy/` and `frontend/static/ol/` for reference. The
backend still serves `/static`, and one test checks it.

## Tests (`tests/`)

| File | Covers |
|------|--------|
| `test_core.py` | Geometry, terrain, slope, routing rules and metrics on synthetic grids |
| `test_routing_speed.py` | Compiled A* against the Python reference, corridor search, long-route speed |
| `test_api.py` | Every endpoint against the real and synthetic datasets |
| `test_assistant.py`, `test_aria_offline.py` | ARIA: wording, follow-ups, place names, sources, no invented numbers |
| `test_ortho.py` | HiRISE photo tile depth, sharper-mosaic fallback, cache headers |

Run them with `python -m pytest`. There are 197 tests; with the data downloaded, they all run.
