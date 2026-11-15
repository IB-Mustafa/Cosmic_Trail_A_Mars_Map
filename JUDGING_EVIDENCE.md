# COSMIC TRAIL: our data check and test evidence

Before submitting, we went through our own project file by file to answer three questions for the
judges. Where does each piece of data come from? Which parts are bundled and static, which are
fetched live, and which are calculated while you use the app? And what can we honestly claim?

## 1. What we checked, and what we didn't

We checked what's in the project: that every file is there, the metadata fields, the product names
we declare, the grid sizes and coverage figures in the metadata, and the code that loads and uses
each dataset.

We didn't re-download every original NASA/USGS product and compare it byte for byte with our
copies. So when we say a dataset comes from a source, we mean we documented it and the metadata
records it, not that an outside auditor certified it. SHA-256 checksums show our files haven't
changed since we built them. They don't prove where the originals came from, or that our processing
is scientifically correct.

We did check every link and citation in our documentation in November 2026. See
[DATA_SOURCES.md](DATA_SOURCES.md).

## 2. Our data, piece by piece

### 2.1 Gale Crater terrain: HiRISE DTMs with a USGS gap fill

Files: `data/hirise_gale/metadata.json`, `data/hirise_gale/analysis.npz`, built by
`scripts/prepare_data.py`.

The dataset is labelled `kind: real_hirise` and merges five HiRISE DTMs:

- `DTEEC_018854_1755_018920_1755_U01.IMG`
- `DTEEC_023957_1755_024023_1755_U01.IMG`
- `DTEEC_009505_1755_009571_1755_U01.IMG`
- `DTEEC_010573_1755_010639_1755_U01.IMG`
- `DTEEC_040770_1755_039280_1755_U01.IMG`

Two more tiles (`DTEEC_024234_1755_024300_1755_U01`, `DTEEC_001488_1750_001752_1750_U02`) were
skipped because they have no valid data inside our study window.

| From the metadata | Value |
|-------------------|-------|
| Study area | 137.35–137.55°E, 4.75–4.45°S |
| Grid resolution | 5 m |
| Grid size | 2,364 × 3,558 cells |
| Total cells | 8,411,112 |
| Valid cells | 8,399,272 (99.86%) |
| From HiRISE | 7,417,993 (88.19%) |
| Filled from the USGS DEM | 993,119 (11.81%) |
| Filled from MOLA | 0 (0%) |
| Slope, 95th percentile | 18.81° |

So the grid isn't 100% HiRISE. 11.81% of the cells come from the USGS MSL Gale Merged DEM 1 m v3,
a HiRISE + CTX + HRSC blend tied to MOLA. We resample it from 1 m to 5 m and blend its edges into
the HiRISE surface. The `usgs_filled` mask in `analysis.npz` says which cells those are.

This is a processed product, not raw instrument output. Our pipeline merges, clips, reprojects and
resamples the DEMs, computes slope, and fills the gaps.

### 2.2 HiRISE photo mosaic

File: `data/hirise_gale/ortho_mosaic.tif`, built by `scripts/build_ortho_mosaic.py`.

| From the metadata | Value |
|-------------------|-------|
| Pixel size | 1 m |
| Coverage of the window | 88.17% |
| Missing source images | None |

The mosaic merges five HiRISE RED orthoimages. The first image wins where they overlap, each one is
histogram-matched to the others, and the result is clipped to the window, so it doesn't cover the
whole area. We show it with one fixed contrast stretch, with no sharpening or upscaling. An optional
0.5 m version can be built from the full-resolution HiRISE images (see
[DATA_SOURCES.md](DATA_SOURCES.md)), and it isn't part of the standard download.

### 2.3 Global elevation: MOLA

File: `data/terrain_context.npz`. This is a processed MOLA grid that gives the 3D globe its heights
outside the study area. It's separate from the 5 m routing grid and much coarser.

### 2.4 Basemap imagery: NASA Mars Trek (live)

Defined in `frontend/src/components/Globe.tsx`:

- the Viking MDIM 2.1 colour mosaic (about 232 m/px);
- MGS MOLA colour-shaded relief (about 463 m/px), in the Whole Mars view.

These tiles are fetched from NASA Mars Trek while the app runs, so they need internet. They aren't
bundled. Without them the globe shows a plain colour, and our own layers still work.

### 2.5 Mineral detection sites

File: `data/minerals/aqueous_minerals.json`. These are 2,417 detection points from Ehlmann & Edwards
(2014), based on CRISM, OMEGA and THEMIS. They mark detection sites, not a continuous mineral map,
and they're bundled, not a live feed.

### 2.6 Geologic units

File: `data/usgs_geologic_units.geojson`, after Tanaka et al. (2014), USGS SIM 3292. The two units
are simplified rectangles, not precisely digitised boundaries.

### 2.7 Curiosity path and landing sites

The proposed Curiosity path has six waypoints. Only Bradbury Landing's coordinate is published, and
the others are approximate. It's NASA's proposed path, not the rover's real track. The landing
sites and place names are bundled reference data, not live positions.

### 2.8 Dune outline

The Bagnold Dunes outline is bundled and approximate. It's for context, not a surveyed or certified
hazard boundary.

### 2.9 Weather and science facts

Files: `app/weather_facts.py`, `app/science.py`. The weather values are published historical figures
stored in code (REMS temperatures from PIA16913, RAD dose from Hassler et al. 2014). They aren't live
Mars weather, and they aren't a REMS/RAD data feed. The science cards are short explanations with
literature references.

### 2.10 Synthetic demo terrain

File: `data/synthetic_demo/metadata.json`. It's labelled `kind: synthetic_demo` and generated
mathematically: random seed 42, a 2,000 × 2,000 grid at 5 m, 99.62% valid. We use it for tests and
as a fallback only. It isn't real Mars terrain.

## 3. Static, live and calculated

"Dynamic" can mean two different things: fetched from a remote service, or calculated by our code.
We keep them apart:

| Part | Comes from | In the app |
|------|------------|------------|
| Gale routing terrain | Bundled `data/hirise_gale/` | Static input, read locally |
| HiRISE photo | Bundled `ortho_mosaic.tif` | Static, served as tiles by our backend |
| MOLA context | Bundled `data/terrain_context.npz` | Static |
| Mineral sites | Bundled JSON | Static |
| Geologic units | Bundled GeoJSON | Static |
| Curiosity path | Bundled GeoJSON | Static reference |
| Dune outline | Bundled GeoJSON | Static, approximate |
| Place names | Bundled with the frontend | Static |
| Weather figures | `app/weather_facts.py` | Static historical values |
| Science cards | `app/science.py` | Static |
| Viking basemap | NASA Mars Trek | **Live**, needs internet |
| MOLA relief basemap | NASA Mars Trek | **Live**, needs internet |
| Terrain and photo tiles | Our backend, from local files | Calculated on request |
| Routes, distances, comparisons | `app/routing.py` | Calculated on request |
| Point lookups, slope checks | `app/terrain.py`, `app/assistant.py` | Calculated on request |
| ARIA answers | `app/assistant.py` and helpers | Rule-based, calculated locally; no language model |

A route is calculated live even though the terrain under it is static, and the basemap is fetched
live while every layer we use for routing stays local.

## 4. Where it happens in the code

| File | Role |
|------|------|
| `scripts/prepare_data.py` | Downloads, merges and fills the terrain; builds the analysis grid |
| `scripts/build_ortho_mosaic.py` | Builds the HiRISE photo mosaic |
| `app/terrain.py` | Loads the terrain and answers point lookups |
| `app/routing.py` | Plans and compares routes |
| `app/context.py` | Local context: geology, minerals, dunes, data source |
| `app/assistant.py` | ARIA's rule-based answers |
| `app/weather_facts.py` | Published weather figures |
| `frontend/src/components/Globe.tsx` | The globe, terrain provider and remote basemaps |
| `frontend/src/api/cosmic.ts` | Frontend calls to the backend |
| `data/hirise_gale/metadata.json` | Provenance, coverage, gap fill and checksums |

Everything uses one coordinate convention: a local equidistant cylindrical frame on the Mars sphere
(R = 3,396,190 m), planetocentric latitude, east-positive longitude. Slope uses the Horn 3×3 method
on the 5 m grid.

## 5. What we can and can't claim

**Supported by our files:**

- The dataset is labelled `real_hirise` and merges five named HiRISE DTMs.
- The grid is 5 m, with the coverage and source shares listed above.
- 11.81% of the grid is filled from the USGS DEM, and that's documented.
- The HiRISE photo is a derived mosaic.
- The MOLA context is separate, and the Mars Trek basemap is live.
- The mineral, geology, path, dune, place-name, weather and science data is bundled.
- The synthetic terrain is labelled as generated.
- Routes and ARIA answers are computed by our own code, on your machine.

**What we don't claim:**

- "Every terrain cell is HiRISE." That's wrong: 11.81% is USGS-filled.
- "All map layers are live NASA data." That's wrong too: most are bundled static files.
- "The Mars weather is live." It isn't. The figures are historical values stored in code.
- "ARIA is a generative AI connected to NASA." It isn't. ARIA is rule-based and offline.
- "The Curiosity line is the rover's exact track." It isn't, and most waypoints are approximate.
- "Geology and dune outlines are surveyed boundaries." They're simplified and approximate.
- "The synthetic demo is real Mars terrain." It isn't.
- "A checksum proves NASA provenance or accuracy." It doesn't.

## 6. Checksums and reproducibility

`metadata.json` records SHA-256 checksums for the source DTMs and the processed grid, and the
synthetic dataset has its own. `scripts/download_data.py` checks the grid's checksum after
downloading. A match shows a file is unchanged since we built it. For formal scientific use, check
the original NASA/USGS products directly.

## 7. Build and test results

| Check | Result |
|-------|--------|
| `npm run build` | Succeeds. Main bundle 829.10 kB (Vite warns about bundles over 500 kB) |
| `python -m pytest` on `main` | 189 tests: 188 passed, 1 failed |
| `python -m pytest` on this branch (adds the HiRISE photo tests) | 197 tests: 196 passed, 1 failed |
| The one failure | `test_long_real_route_is_fast_and_near_optimal`, a timing test that expects a full-length route in under 2 s. On our laptops one route took about 4–5 s (3.9 s on the laptop we used for the final check). The route itself passes the correctness checks in the same test. |
| Backend on Windows | Confirmed: it starts and serves the app on Windows (`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`) |
| Browser | Confirmed: the app works in Microsoft Edge (Chromium) |

The test warnings are deprecation notices from Starlette, anyio and rasterio, not failures.

## 8. In a few sentences, for the judges

COSMIC TRAIL plans routes over Gale Crater on a 5 m grid that we built from five HiRISE DTMs, with
the gaps (11.81%) filled from the USGS Gale DEM, so it's 99.86% valid. We add a HiRISE photo mosaic,
MOLA heights for the rest of the globe, and live NASA Mars Trek imagery for the basemap. Minerals,
geology, the Curiosity path, dunes, place names, weather and science facts are bundled reference
data, with their approximations stated. Routes and terrain checks are calculated on your machine
from local data, and our assistant ARIA is rule-based, not a language model. The synthetic dataset
is only for tests, and we never present it as real terrain.
