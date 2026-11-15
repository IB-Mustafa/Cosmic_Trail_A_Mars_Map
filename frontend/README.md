# COSMIC TRAIL frontend

React 18 + TypeScript + Vite, with CesiumJS (through Resium) for the globe, Zustand for state and
Recharts for the elevation chart. For the full setup, see [../LOCAL_SETUP.md](../LOCAL_SETUP.md).

```powershell
# backend first (repo root, venv active)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# then the frontend
cd frontend
npm install
npm run dev -- --host 127.0.0.1    # http://127.0.0.1:5173
```

Put `VITE_API_BASE=http://127.0.0.1:8000` in `frontend/.env.local`. Without it the app calls
`http://localhost:8000`, which can resolve to IPv6 on Windows and miss the backend.
`npm run build` type-checks and builds into `dist/`.

## Where things are

| File | What it does |
|------|--------------|
| `src/App.tsx`, `src/App.css` | Layout: full-screen globe with glass panels; the one font (Space Grotesk, bundled) |
| `src/api/cosmic.ts` | Every backend call; terrain tiles are fetched at most 4 at a time and paused while a route computes |
| `src/store/layerStore.ts`, `routeStore.ts` | Zustand: layers and view, dataset, A/B, route results |
| `src/components/Globe.tsx` | Cesium viewer: terrain, Mars Trek basemaps, HiRISE overlays and photo, routes, markers, info cards |
| `src/components/MarsLabels.ts`, `src/labelStyle.ts` | One label style for every name, and the declutter that keeps labels from overlapping |
| `src/components/MineralPoints.ts` | Mineral detection points |
| `src/components/ZoomAids.tsx` | HiRISE photo zoom stop, "Max HiRISE detail" chip, scale bar |
| `src/components/RoutePanel.tsx` | A/B inputs and picking, Find Route, results and comparison |
| `src/components/ElevationChart.tsx`, `ResizablePanel.tsx` | Resizable elevation profile coloured by slope; GeoJSON / briefing export |
| `src/components/Inspector.tsx` | Hover bar: position, elevation, slope and data source under the cursor |
| `src/components/LayerControls.tsx` | Layer toggles |
| `src/components/Chatbot.tsx` | ARIA chat panel |
| `src/mapFrame.ts` | Centres views on the part of the map that panels don't cover |
| `src/mars.ts`, `src/data/` | Mars sphere and coordinate convention, IAU place names, NASA landing sites |

## Notes

- **No Cesium ion token.** The globe is a Mars sphere (R = 3,396,190 m). Heights come from the
  backend's height tiles: the 5 m grid in the routing area, and MOLA elsewhere, blended over 300 m
  at the edge. Heights are true (1×).
- **Basemap.** NASA Mars Trek tiles (Viking MDIM 2.1 colour; MOLA colour relief in the Whole Mars
  view) are the only thing that needs internet.
- **Rendering.** It renders at the screen's pixel ratio, capped at 1.25, with 2× MSAA. On an Intel
  Iris Xe laptop that kept the Gale view at the same frame rate as before while looking sharper.
  The tile error is 1.5, and 300 terrain tiles stay cached.
- **HiRISE photo.** Its tiles come from the backend down to the mosaic's native resolution. Over
  the photo, the camera stops where one photo pixel would cover about 1.5 screen pixels.
- **Labels.** They are white with a black outline, and small marker labels get a dark background.
  Each category shows from its own zoom level. Landing sites, science sites, waypoints and minerals
  are placed before place names, and anything that would overlap is hidden. Clicking a name opens
  the same card as its marker.
- **Picking A/B.** A picked point is checked against the routable area, then against the backend
  lookup. Steep points are accepted with a note, because the router snaps to the nearest walkable
  cell within 300 m.
- **Travel time** is the 3D route length divided by 4 cm/s (Curiosity's top speed), so it's a lower
  bound.
- **ARIA** sends each question with the point at the map centre, the last route's summary and the
  last few messages. All the logic is in the backend, which is rule-based and offline.
- **The old OpenLayers page** is kept in `legacy/index.html`. `static/ol/` stays because a backend
  test still checks it.
