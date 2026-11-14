# COSMIC TRAIL — Scientific Limitations

This document lists known limitations of COSMIC TRAIL's terrain analysis and
routing. We state these honestly so judges, educators, and users understand
what the tool can and cannot do.

---

## Terrain Data Limitations

### HiRISE DTM artefacts
- HiRISE DTM products may contain jitter artefacts, shadow occlusion patches,
  and areas where stereo correlation failed (returned as NoData).
- NoData cells inside the analysis grid are filled from the USGS MSL Gale
  Merged DEM (see "Gap fill" below). Any cell still without elevation is
  treated as impassable. Filled areas are not labelled as specific geological features.

### Resolution mismatch
- HiRISE DTM post spacing is ~1 m. COSMIC TRAIL resamples to 5 m cells
  for routing. Fine-scale obstacles (rocks < 5 m) are invisible to the router.
- Real rover or EVA traverse safety requires much finer hazard analysis than
  5 m-cell routing can provide.

### Projection accuracy
- The local equidistant cylindrical projection introduces a scale error that
  grows with distance from the projection centre.
- At the 5 km edge of the 10 km × 10 km study window the scale error is
  approximately 0.05% — negligible for demonstration, but non-zero.
- Mars is treated as a sphere (R = 3,396,190 m). The actual Mars geoid
  departs from a sphere by up to ~20 km.

### Gap fill (USGS MSL Gale Merged DEM)
- Gap areas filled with USGS MSL Gale Merged DEM 1m v3 (HiRISE+CTX+HRSC
  blend, 1 m/pixel). No artificial detail added.
- **What is filled.** The two merged HiRISE DTMs (DTEEC_023957_1755 and
  DTEEC_009505_1755) leave about 16% of the 5 m analysis grid without
  elevation (stereo gaps and the areas between the image strips). Only those
  cells are filled; values from the HiRISE tiles are never replaced. Source:
  `MSL_Gale_DEM_Mosaic_1m_v3.tif`, USGS Astrogeology Science Center.
- **Effective resolution varies.** 1 m is the mosaic's grid spacing. Where
  the mosaic itself was built from CTX or HRSC rather than HiRISE, the real
  detail is coarser than 1 m. In the current build, slopes in filled areas
  (median 4.4°) are similar to slopes in HiRISE areas (median 3.8°).
- **Boundary blending.** The USGS mosaic sits a few metres higher than our
  HiRISE tiles where both exist (HiRISE − USGS ≈ +2 to +20 m, 5th–95th
  percentile). To avoid a step at gap edges, that offset is spread smoothly
  across each gap (Laplace/harmonic interpolation) and added to the USGS
  values. The filled heights are therefore adjusted to match the HiRISE
  tiles, not the USGS values as published. Gap edges remain slightly rougher
  than surrounding terrain (95th-percentile slope ~24° vs ~16°).
- **Fallback.** If the USGS file is not present, `prepare_data.py` falls back
  to the MOLA 463 m global DEM. MOLA-filled areas are ~90× coarser, so their
  slopes are smoothed and under-state real steepness. `metadata.json`
  (`fill_source`) and the map legend say which source was used.
- **How to tell them apart.** Filled cells are stored in `analysis.npz`
  (`usgs_filled`, `mola_filled`), counted in `metadata.json` (`stats`,
  `usgs_fill`), shown with blue hatching on the map (toggle "🛰 Gap-fill
  areas"), and reported as the elevation source when hovering over the map.
- **Horizontal offset between products.** Where both exist, the USGS mosaic places
  features ~30–45 m east (and up to 30 m N/S) of the HiRISE DTMs (cross-correlation
  of 805 m patches, 2026-11-12). Each part of the grid follows its own source, so
  gap-fill boundaries can show a small step.

### HiRISE DTM coverage (wider Gale area)
Searched the official HiRISE PDS cumulative DTM index
(`https://www.uahirise.org/PDS/INDEX/DTMCUMINDEX.TAB`, 2026-11-12) for lon
137.1–137.8°E, lat 5.2–4.0°S: **18 elevation DTMs** intersect it — the 4 already used
or tried, plus 14 new (13 stereo pairs; 040770/039280 exists as both A01 and U01).
All are listed with sizes and PDS paths in `ADDITIONAL_DTM_FILES`
(`scripts/prepare_data.py`). They are **not downloaded automatically** (128–833 MB each).

- **Would improve the current study window** (137.35–137.55°E, 4.45–4.75°S):
  018854, 010573, 040770, 009149, 009650 (and slivers of 019698, 011417). Two of them
  cover Bradbury Landing, which is USGS-filled today.
- **Outside the current window** (merged only if `STUDY_WINDOW` is widened): 062963
  (Peace Vallis, 2 m posts), 018788, 012551, 006855, 012340, 008147.
- **No HiRISE DTM coverage** in the wider window (from index bounding boxes, which
  over-state coverage because strips are narrow and tilted — at most ~44% of the window
  is inside any footprint):
  - the western edge, 137.1–137.2°E north of ~4.7°S;
  - north-east Aeolis Palus, north of ~4.3°S between 137.4 and 137.8°E;
  - the south-east quarter, east of ~137.5°E and south of ~4.75°S (central Aeolis Mons).
- **Why:** HiRISE DTMs exist only where a stereo pair was deliberately targeted and a
  team produced the DTM (each strip ~5–6 km × 10–30 km). In Gale these cluster on the
  former MSL candidate landing ellipse and Curiosity's traverse; the rest of the crater
  has HiRISE images but no released stereo DTM. The USGS Gale mosaic (HiRISE+CTX+HRSC)
  or MOLA (463 m) are the only elevation sources there.
- **Grid size if widened:** the full 0.7° × 1.2° window at 5 m would be ~8 300 × 14 200
  cells (~118 M), far beyond the current 4.1 M — routing time and memory would need to
  be revisited before widening `STUDY_WINDOW`.

### 3D globe display (terrain and vertical exaggeration)
- **Exaggeration is visual only.** The "3D Exaggeration" slider (1×–5×, default 3×)
  stretches heights relative to the study-area floor (median grid height ≈ −4 482 m).
  At 3× a 10° slope *looks* like ~28°, at 5× like ~41°. Routing, slope thresholds, the
  elevation chart, lookups and every reported number use true (1×) heights. Do not judge
  traversability from the 3D view.
- **Mixed resolutions.** Inside the routing area the globe uses the 5 m analysis grid
  (HiRISE + USGS gap fill). Outside it uses MOLA: 463 m around Gale (131–144°E,
  11°S–2°N) and MOLA averaged to 1/8° (~7.4 km) elsewhere, so Mount Sharp, the crater rim
  and distant terrain are much smoother than the routing area. MOLA's averaged global grid
  under-states extremes (e.g. Hellas floor ~−7.4 km vs ~−8.2 km in the full DEM).
- **Edge blend.** Within 300 m of the routing grid's edge, grid and MOLA heights are
  blended linearly to avoid a wall. Near Bradbury Landing they differ by only a few metres,
  but elsewhere (up to ~20 m where checked) the blend band shows a smoothed ramp, not
  real terrain.
- **Height datum.** All heights are areoid-referenced (MOLA convention) and drawn on the
  IAU Mars sphere (R = 3 396 190 m). Fine for relief, but absolute heights above the
  sphere are not physical radii.
- **Label occlusion is approximate.** Place names behind terrain are hidden with one ray
  test per label against the currently loaded terrain tiles; while tiles are still loading
  a name can briefly show or hide incorrectly.
- **Basemap.** The colour basemap (Viking MDIM 2.1, 232 m/px via NASA Mars Trek) is far
  coarser than HiRISE and needs internet. Offline, the globe shows a plain colour; terrain,
  overlays, labels and routing still work.
- **Build step.** The MOLA context (`data/terrain_context.npz`) is built separately with
  `scripts/build_terrain_context.py` (needs the 2 GB MOLA global DEM); `prepare_data.py`
  does not rebuild it. Without the file the globe stays flat.

---

### Minerals layer (aqueous-mineral detection sites)
- **What it is.** 2 417 detection sites from the global compilation by Ehlmann & Edwards
  (2014, *Annu. Rev. Earth Planet. Sci.* 42:291–315), served by NASA Mars Trek
  ("Aqueous Mineral Distribution"), from MRO CRISM, Mars Express OMEGA and Mars Odyssey
  THEMIS: phyllosilicates 1 648, chlorides 344, sulfates 207, silica 182, carbonates 36.
  Bundled locally by `scripts/build_mineral_points.py` (`data/minerals/aqueous_minerals.json`).
- **Not a mineral map.** Each point marks a published detection site (≈ ±0.01°), not the
  extent of a deposit. Absence of a point does not mean absence of the mineral.
- **Gale coverage is sparse.** 7 sites lie within ~150 km of Bradbury Landing and **none
  inside the routing area**; the nearest is a phyllosilicate detection on Mount Sharp's
  flank (137.64°E, 5.33°S). The layer gives regional context, not route-scale geology.
- **Why not a CRISM raster.** The requested Mars Trek layer `MRO_CRISM_MSW_226PPD_v02`
  does not exist (HTTP 404, checked 2026-11-13), and Mars Trek has no CRISM mineral
  raster covering Gale (its only CRISM indicator rasters cover Mars Chart 18 and tile
  1303). Pixel-level CRISM targeted products from PDS would be needed for that.
- **Colours** are the product's own (`jC_fillclr`): phyllosilicate blue, sulfate pink
  (#ff6699 — the Trek description says "orange"), silica purple, chloride yellow,
  carbonate green.
- **Placement.** Points sit at the MOLA height of the site (exaggerated like the terrain).

---

## Routing Algorithm Limitations

### Slope threshold sources
- Slope thresholds are sourced from Apollo EVA traverses (EPSC2024) and the
  NASA MSL Engineering User Guide. These values have not been validated
  specifically for this terrain model or for future Mars suit designs.

### Horn slope formula
- COSMIC TRAIL uses the Horn (1981) 3×3 finite-difference formula.
- Border cells and cells adjacent to NoData are set to NaN (impassable)
  because the full 3×3 neighbourhood is unavailable.
- This may exclude navigable border cells unnecessarily.

### No diagonal corner-cutting
- The A* implementation prohibits diagonal steps when both orthogonal
  neighbours in that diagonal direction are blocked. This avoids squeezing
  through a 1-cell gap, which is physically plausible but may make some
  routes longer than a real rover or astronaut would walk.

### No dynamic obstacles
- Routes do not account for dust storms, loose regolith, subsurface voids,
  radiation exposure, or time-of-day visibility. These factors are real
  constraints for Martian EVA that are beyond the scope of a 2D terrain
  planner.

### 2D only
- Route length is computed in the local equidistant cylindrical plane
  (planimetric) plus a geodesic approximation. The app also reports a 3D
  surface-following length estimated from elevation changes along the path,
  but this is an approximation, not a true surface integral.

---

## Science Card Limitations

### Coordinate confidence levels
Each science card has a `coord_confidence` field:
- **published** — coordinate taken from a peer-reviewed paper or official
  NASA mission report.
- **approximate** — coordinate estimated from map context; ± few hundred metres.
- **unverified** — coordinate sourced from general descriptions; not confirmed
  against PDS labels or landing site reports.

Cards with `unverified` coordinates should not be used for precise navigation.

### Mineralogy ≠ past water ≠ life
- Science cards describe mineral evidence (phyllosilicates, sulphates) that
  scientists interpret as indicators of past aqueous processes.
- **This does not prove liquid water existed on Mars.**
- **This does not prove past or present life on Mars.**
- Each card includes explicit caveats stating this.

### Literature currency
- Science card facts are sourced from papers published up to 2024.
- Mars exploration is ongoing. Newer findings may refine or contradict
  the information displayed.

---

## ARIA Assistant Limitations
- **Rule-based, not AI.** ARIA (`app/assistant.py`) picks one intent per question by
  keyword and builds the answer from loaded data. It does not understand free text, keep
  conversation memory, or combine several questions. Unmatched questions fall back to the
  Mission Guide's curated facts.
- **"Here" is the map centre** (or a named place in the question: Bradbury Landing, Mount
  Sharp, Aeolis Palus). Outside the 5 m grid it only gives a coarse MOLA height.
- **Never a safety verdict.** Slope answers compare 5 m slopes with the router's 10° caution
  and 15° limit. Boulders, loose sand, dust and anything below 5 m are not in the data.
  Directional answers ("walk north") sample a straight 500 m line, not a planned route.
- **Weather / radiation.** No REMS or RAD data are loaded; ARIA says so and quotes one
  published figure (RAD surface dose-equivalent ≈ 0.64 ± 0.12 mSv/day, Hassler et al. 2014).
- **Minerals.** Nearest sites come from the detection-site compilation (see "Minerals layer");
  ground-truth facts come from the cited science cards.

---

## Mission Guide Limitations

The Mission Guide is a **rule-based keyword lookup**, not an AI:
- It matches your query against a fixed list of keywords.
- It returns pre-written text — it does not generate new information.
- It cannot answer questions outside its keyword list.
- It cannot reason about combinations of topics.
- It explicitly labels itself as a rule-based system in every response.

---

## What COSMIC TRAIL Does Not Do

| Claim | Reality |
|-------|---------|
| "Safest route" | No route is certified safe. The tool finds terrain-weighted paths. |
| "NASA-approved" | COSMIC TRAIL is a student project, not a NASA product. |
| "Guaranteed safe for EVA" | No terrain planning tool guarantees EVA safety. |
| "Real-time data" | All data is static; no live updates. |
| "Subsurface hazards" | The tool has no subsurface information. |
| "Dust / weather" | No atmospheric or seasonal modelling. |
| "AI-generated science facts" | The Mission Guide is rule-based; science cards cite peer-reviewed literature. |

---

## Synthetic Data Warning

When the synthetic demo dataset is active, the app displays a prominent
orange warning banner. The synthetic dataset:
- Is mathematically generated from a fixed random seed
- Does not represent any real Mars terrain
- Produces routing results that have no scientific meaning
- Is stored separately from real data and can never be confused with it

---

*COSMIC TRAIL was built for the NASA Space Apps 2026 hackathon by Team
CosmicGirls. It is intended as an educational prototype, not an operational
mission-planning system.*
