# COSMIC TRAIL frontend (React + TypeScript + Vite + CesiumJS)

```bash
# 1. backend (from the repo root)
uvicorn app.main:app            # http://localhost:8000

# 2. frontend
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Set `VITE_API_BASE` to point at a different backend (default `http://localhost:8000`).

## Structure

| File | Role |
|---|---|
| `src/api/cosmic.ts` | All backend calls (`/api/health`, `/api/datasets`, `POST /api/route`, layers, science cards) |
| `src/store/layerStore.ts` | Zustand: layer visibility |
| `src/store/routeStore.ts` | Zustand: dataset, start/end, route response, active route |
| `src/components/Globe.tsx` | Cesium globe: HiRISE + gap-fill overlays, routes, pins |
| `src/components/RoutePanel.tsx` | Start/end inputs (or pick on globe), Find Route, results |
| `src/components/ElevationChart.tsx` | Recharts elevation profile, coloured by slope band |
| `src/components/LayerControls.tsx` | Layer toggles |

## Notes

- **No Cesium ion token needed.** The globe is a Mars sphere (R = 3 396 190 m, same as
  the backend projection) with real 3D terrain from the backend (see below).
- **Mars basemap** = NASA Mars Trek WMTS tiles of the Viking MDIM 2.1 colour mosaic
  (232 m/px, no token). This is the only part that needs internet — offline, the globe
  shows a plain base colour and everything from the backend still works.
- The camera starts over Gale Crater (137.4°E, 4.6°S, 50 km altitude). Sun, moon and
  Earth-style atmosphere glow are turned off. The camera is never restricted.

## 3D terrain and vertical exaggeration

- Heights come from the backend (`/api/datasets/{id}/terrain/{z}/{x}/{y}`, 65×65 float32
  tiles in Cesium's geographic tiling) through a `CustomHeightmapTerrainProvider`:
  the 5 m analysis grid (HiRISE + USGS gap fill) inside the routing area, MOLA 463 m
  around Gale and MOLA 1/8° elsewhere, blended over 300 m at the grid edge.
  Build the MOLA part once with `python scripts/build_terrain_context.py`; without it
  the globe stays flat (the slider shows "flat").
- "3D Exaggeration" slider: 1×–5×, default 3×. It sets `scene.verticalExaggeration`
  relative to the study-area floor (median grid height ≈ −4 482 m), so the Gale floor
  stays put and relief above/below it is stretched. **Display only** — routing, the
  elevation chart, lookups and all numbers use true heights.
- `globe.depthTestAgainstTerrain` is on. Pins, the Gale marker and labels are placed at
  the rendered surface height (`globe.getHeight`, refreshed when tiles load or the
  exaggeration changes). Cesium's `CLAMP_TO_GROUND` was tried but settled on wrong
  heights with this terrain provider, leaving pins floating.
- Place names behind terrain are hidden: below 1 000 km camera height each candidate
  label is checked with a ray from the camera; if terrain is hit first, it is not shown.
- HiRISE / gap-fill overlays are textured ground rectangles classified onto the terrain.
- Terrain tiles are fetched at most 4 at a time, and none are started while a route is
  computing (tile generation and the A* search share the backend's Python GIL; together
  a 9 s route took ~33 s, with the pause ~12 s in a headless test).

## Minerals layer

- "🔬 Minerals (CRISM/OMEGA)" pill → `GET /api/layers/minerals`: 2 417 aqueous-mineral
  detection sites (Ehlmann & Edwards 2014; CRISM, OMEGA, THEMIS via NASA Mars Trek),
  bundled by `scripts/build_mineral_points.py`. Drawn as a `PointPrimitiveCollection`
  (`src/components/MineralPoints.ts`) at each site's MOLA height, exaggerated like the
  terrain; click a point for its class, location and source.
- The legend (shown while the layer is on) uses the product's own colours and states that
  these are detection sites, not a mineral map, and how many fall inside the routing area
  (none for the current dataset). See SCIENTIFIC_LIMITATIONS.md "Minerals layer".

## ARIA assistant

- `src/components/Chatbot.tsx`: floating "🤖 ARIA" button (bottom-right) opening a glass chat
  panel with three quick actions. Each question is sent to `POST /api/assistant/chat` with the
  terrain point at the map centre (`getMapCenter()` in Globe.tsx), the dataset id and a summary
  of the active route (no per-cell arrays).
- Replies show data-source badges (📡 HiRISE, 🗺 USGS Gale DEM, 🛰 MOLA, 🔬 CRISM/OMEGA,
  🧭 Route result, 📚 Published studies), a confidence level, the location used and a caveat.
- Rule-based and offline (backend `app/assistant.py`) — no language model.

## Place names (IAU/USGS Gazetteer)

- `src/data/mars_labels.json` — 2 055 official Mars names (IAU-adopted), bundled locally.
  Rebuild from the USGS download with
  `python scripts/build_mars_labels.py MARS_nomenclature_center_pts.zip`
  (from https://planetarynames.wr.usgs.gov/GIS_Downloads).
- Level of detail: a name shows when its diameter ≥ camera height ÷ 40 (globe view:
  terrae/planitiae; 900 km: Gale-region valles and montes; a few km: small craters).
- Overlap: names are placed largest-first; a name whose box would overlap another name,
  a pin, the Gale marker or a floating panel is hidden (`src/components/MarsLabels.ts`).
- Gale Crater has its own clickable marker (IAU centre 5.37°S, 137.81°E) and a
  "Go to Gale Crater" button.

## Coordinates and overlay georeference

- One convention everywhere: planetocentric latitude, east-positive longitude −180…180°,
  Mars sphere R = 3 396 190 m (`src/mars.ts`). The gazetteer's 0–360°E longitudes are
  converted at build time; Mars Trek tiles, HiRISE/USGS DTMs and backend coordinates
  already use it.
- The HiRISE PNG layers are placed from the terrain file metadata (`/api/datasets/{id}/metadata`:
  local eqc CRS + grid origin, cell size and size, pixel-edge registration) —
  `georefFromMetadata()` in `src/api/cosmic.ts`.
- Checked against the source DEMs read through their own CRS (best-fit shift of the
  overlay grid vs the source, 5 m search steps):
  Bradbury Landing vs USGS MSL Gale DEM → 0 m (r = 0.9998);
  a 400 m crater at 137.5447°E, 4.4647°S vs HiRISE DTEEC_009505 → 0 m (r = 0.9999);
  the same lon/lat → backend lookup cell matches exactly.
- Known source-data limitation: where both exist, the USGS mosaic sits ~30–45 m east
  (and up to 30 m N/S) of the HiRISE DTMs, so gap-fill boundaries can show a small step.

## Routable area and picking

- The dashed outline is the analysis grid (every cell has elevation; only the outer
  1-cell border lacks slope). It is tinted while picking A/B.
- A picked point is checked first against the footprint, then with the backend's
  `/lookup` (status `ok` required) before the pin moves. Steep cells are accepted with
  a note: the router snaps to the nearest passable cell within 300 m.
- Slope colours in the chart use the backend's own thresholds from `params_used`
  (caution 10°, max 15°), so the chart always matches the router.
- Travel time = 3D route length ÷ 4 cm/s (Curiosity's top speed, NASA MSL spec): a lower bound.
- The "Curiosity traverse" toggle is disabled: the backend has no traverse data yet.
- The previous OpenLayers UI is saved in `legacy/index.html`. `static/ol/` stays because
  the backend tests check it.
