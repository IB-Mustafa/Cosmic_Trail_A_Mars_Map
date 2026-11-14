# COSMIC TRAIL — Architecture

## Overview

COSMIC TRAIL is a single-machine, fully offline web application.  
No data leaves your computer at runtime.

```
Browser (index.html + OpenLayers)
         │
         │  HTTP (localhost only)
         ▼
FastAPI backend (Python)
    ├── TerrainDataset  ─── analysis.npz (elevation + slope arrays)
    ├── A* Router       ─── Horn slope, 8-connected grid
    ├── Science cards   ─── in-memory, curated
    ├── Mission Guide   ─── rule-based keyword lookup
    └── SQLite          ─── data/plans.db  (saved plans)
```

---

## Backend (Python / FastAPI)

### `app/geo.py` — Planetary geometry

| Symbol | Value |
|--------|-------|
| `MARS_SPHERE_RADIUS_M` | 3,396,190 m (MOLA/HiRISE map-projection sphere) |
| `MARS_MEAN_RADIUS_M` | 3,389,500 m (volumetric mean, for reference only) |

**`LocalEqc(lat0, lon0, radius)`** — frozen dataclass  
Local equidistant cylindrical projection centred on (lat0, lon0):

```
x = R · cos(lat₀) · (lon − lon₀) · π/180
y = R · (lat − lat₀) · π/180
```

Methods: `forward(lon, lat) → (x, y)`, `inverse(x, y) → (lon, lat)`,
`scale_error_at(y)`.

**`haversine_m(lon1, lat1, lon2, lat2)`** — Mars-sphere great-circle distance.

---

### `app/terrain.py` — Terrain data loading

**`Grid(x_min, y_max, cell, width, height)`** — dataclass  
Converts between (row, col) and (x, y) in local eqc metres.

**`TerrainDataset(folder)`** — reads `metadata.json` and `analysis.npz`.  
Key methods:
- `valid_mask()` — boolean array; True where elevation and slope are finite
- `lookup(x, y)` — returns elevation, slope, passability at a point
- `stats()` — coverage fraction, elevation range, slope p95
- `to_lonlat(x, y)` / `from_lonlat(lon, lat)` — coordinate conversion

---

### `app/routing.py` — A* path-finding

**Horn slope** (Horn 1981):
```
slope_deg = atan(√(fx² + fy²)) · 180/π
fx = [(z[r-1,c+1] + 2·z[r,c+1] + z[r+1,c+1]) − (z[r-1,c-1] + 2·z[r,c-1] + z[r+1,c-1])] / (8·cell)
fy = [(z[r+1,c-1] + 2·z[r+1,c] + z[r+1,c+1]) − (z[r-1,c-1] + 2·z[r-1,c] + z[r-1,c+1])] / (8·cell)
```
Center cell is NOT used. Border and NoData-adjacent cells → NaN (impassable).

**A\* grid**:
- 8-connected; step costs are Euclidean cell distances (1.0 or √2 for diagonals)
- Diagonal steps blocked when either orthogonal neighbour is impassable
  (no corner-cutting)
- Heuristic: Euclidean distance to goal (admissible)

**Cost models**:
- `shortest` — cost = step length in metres
- `terrain` — cost = step length × (1 + slope_weight × slope_fraction) + climb/descent weights

**`RouteParams`** (defaults):

| Parameter | Default | Note |
|-----------|---------|------|
| `max_slope_deg` | 15° | Apollo EVA actual traverses (EPSC2024) |
| `caution_slope_deg` | 10° | Warning threshold — MSL moderate slope threshold (NASA MSL Engineering User Guide) |
| `slope_weight` | 4.0 | Penalty multiplier |
| `climb_weight_per_m` | 2.0 | Extra cost per metre climbed |
| `descent_weight_per_m` | 0.5 | Extra cost per metre descended |

**Route comparison**:
- Hausdorff distance computed between route cell lists
- Routes within 2 cells Hausdorff AND < 1% length difference → "equivalent"
- Identical check prevents showing duplicate route visualisations

---

### `app/science.py` — Science cards and Mission Guide

**Science cards** (`ScienceCard` NamedTuple):
- card_id, site, lon, lat, coord_confidence, summary, detail, tags, sources, caveats
- Coordinates from published landing site reports or peer-reviewed papers
- Each card has explicit mineralogy ≠ life caveats

**Mission Guide** (`mission_guide_query`):
- Rule list: `[(keywords, card_ids, response_text)]`
- Returns matched cards, unmatched note if no match, and always includes:
  `"Mission Guide is a rule-based lookup — NOT an AI."`

---

### `app/db.py` — Plan persistence

SQLite database at `data/plans.db`.

Schema:
```sql
CREATE TABLE plans (
    id          TEXT PRIMARY KEY,  -- UUID
    name        TEXT NOT NULL,
    dataset_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    start_lon   REAL,
    start_lat   REAL,
    end_lon     REAL,
    end_lat     REAL,
    route_mode  TEXT,
    route_data  TEXT,  -- JSON
    params      TEXT,  -- JSON
    notes       TEXT
);
```

Exports: `export_geojson(plan)` → GeoJSON FeatureCollection,
`export_briefing(plan, meta)` → plain-text mission brief.

---

### `app/main.py` — FastAPI application

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve `frontend/index.html` |
| `/static/*` | GET | Serve OpenLayers and static assets |
| `/api/health` | GET | Health check |
| `/api/datasets` | GET | List loaded datasets |
| `/api/datasets/{id}/metadata` | GET | Full metadata.json |
| `/api/datasets/{id}/provenance` | GET | Provenance and checksums |
| `/api/datasets/{id}/integrity` | GET | SHA-256 integrity checks |
| `/api/datasets/{id}/layers/{name}` | GET | PNG layer (hillshade/elevation/slope/thumbnail) |
| `/api/datasets/{id}/lookup` | GET | Terrain lookup by lon/lat |
| `/api/route` | POST | Compute A* route |
| `/api/science/cards` | GET | All science cards |
| `/api/science/cards/{id}` | GET | Single card |
| `/api/guide/query` | POST | Mission Guide query |
| `/api/plans` | GET / POST | List / create plans |
| `/api/plans/{id}` | GET / PATCH / DELETE | CRUD |
| `/api/plans/{id}/export/geojson` | GET | Export GeoJSON |
| `/api/plans/{id}/export/briefing` | GET | Export plain text |

CORS is set to `allow_origins=["*"]` for local development.

---

## Frontend (Vanilla JS + OpenLayers 10.11.0)

Single HTML file: `frontend/index.html`  
No build step. No Node.js. No npm.

**Map**: `ol.layer.Image` with `ol.source.ImageStatic` loads a PNG layer from
the backend. The projection is a custom `MARS-EQC` registered with OpenLayers,
with extent = grid extent in local eqc metres.

**Route rendering**: Two `ol.layer.Vector` layers:
- Blue dashed line = shortest route
- Orange solid line = terrain-weighted route

**Coordinate conversion** in the browser uses the local eqc formula directly
(no PROJ, no server round-trip):
```js
const lon = crs.lon0 + (x / (R * Math.cos(lat0r))) * 180 / Math.PI;
const lat = crs.lat0 + (y / R) * 180 / Math.PI;
```

**Offline capability**: After initial load, all data comes from localhost.
No external requests are made at runtime.

---

## Data Flow

```
User clicks map
  → JS converts pixel → local eqc (x, y)
  → inverse formula → (lon, lat)
  → filled into form fields
  → user clicks Compute Route
  → POST /api/route { dataset_id, start, destination, mode, params }
  → backend: forward lon/lat → local eqc (x, y)
  → nearest_passable() snaps to grid
  → passable_mask() builds boolean array
  → _astar() runs A* → cell list
  → route_metrics() computes stats + xy + lonlat + profiles
  → JSON response
  → JS draws LineString features on OL vector layers
  → canvas profile chart drawn
```

---

## Offline Architecture

```
internet ───✗───  (blocked at runtime)

disk
├── frontend/static/ol/ol.js       OpenLayers, bundled
├── data/synthetic_demo/           synthetic terrain PNGs
│   elevation.png, slope.png, hillshade.png
│   analysis.npz (elevation + slope arrays)
└── data/plans.db                  SQLite, local plans

browser ←──HTTP──→ uvicorn (127.0.0.1:8000)
```

The app works with no internet once installed, provided the synthetic demo
terrain has been generated.

---

## Test Coverage

52 unit tests in `tests/test_core.py` cover:
- `geo.py`: LocalEqc, haversine, validate_lonlat, wrap180
- `terrain.py`: Grid, TerrainDataset, Horn slope (flat, gradient, NoData, border)
- `routing.py`: passable_mask, classify_cell, A*, route_metrics, compare_routes,
  explain_tradeoff, rasterize_polygons, RouteParams

Tests use an in-memory synthetic dataset (`_make_synthetic_ds`) with a known
2° N-S slope plane so assertions can be exact.
