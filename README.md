# 🚀 COSMIC TRAIL — Offline Marswalk Planner

**Team CosmicGirls · NASA Space Apps 2026**  
Challenge: *Interplanetary Survival Guide: Martian Map*

---

## NASA Data Sources

COSMIC TRAIL integrates all five official NASA Space Apps resources for this challenge
(details and caveats in [DATA_SOURCES.md](DATA_SOURCES.md)):

| Resource | URL | How COSMIC TRAIL Uses It |
|----------|-----|--------------------------|
| Mars Trek | [trek.nasa.gov/mars](https://trek.nasa.gov/mars) | Map tile imagery for 3D Mars globe |
| USGS Planetary Mapping | [astrogeology-usgs.hub.arcgis.com](https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars) | Geologic unit polygons for Gale Crater |
| Curiosity Proposed Path | [science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp](https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/) | Reference traverse overlay on map |
| NASA Worldview | [worldview.earthdata.nasa.gov](https://worldview.earthdata.nasa.gov/) | Dust storm hazard context |
| Perseverance Raw Images | [mars.nasa.gov/mars2020/multimedia/raw-images](https://mars.nasa.gov/mars2020/multimedia/raw-images/) | Surface imagery science context |

---

## What is COSMIC TRAIL?

COSMIC TRAIL is a fully offline Mars terrain route-planning tool.  
It reads real NASA HiRISE/MOLA elevation data, runs A* path-finding over
the terrain, and shows you two routes — the **shortest path** and the
**terrain-weighted path** (which avoids steep slopes) — so you can compare
the trade-offs before a planned Marswalk.

The tool is a **prototype for education and demonstration**. It is not an
engineering tool and no route it outputs is certified safe for real EVA or
rover operations.

---

## Quick Start (teammates)

You need **Git**, **Python 3.11+** and **Node.js 18+**. The code is on GitHub; the
data (about 236 MB) is on Hugging Face because it is too large for Git.

### 1. Clone the repo

```bash
git clone https://github.com/IB-Mustafa/Cosmic_Trail_A_Mars_Map.git
cd Cosmic_Trail_A_Mars_Map
```

### 2. Create a Python environment and install the backend

```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
pip install -U huggingface_hub      # provides the `hf` download command
```

> Windows: if PowerShell refuses to run `Activate.ps1`, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` first.

### 3. Download the data from Hugging Face

Dataset: <https://huggingface.co/datasets/irhabatool/cosmic-trail-data> (public, no login needed).

```bash
# Everything the app needs (~236 MB): terrain grids, 3D globe heights,
# HiRISE photo mosaic, map overlays, synthetic demo.
hf download irhabatool/cosmic-trail-data --repo-type=dataset --local-dir data --exclude "hirise_gale/raw/*"
```

This creates `data/hirise_gale/`, `data/synthetic_demo/`, `data/terrain_context.npz`
and the GeoJSON/minerals files. Only add the raw source files (~9.5 GB) if you want to
rebuild the processed data yourself — see [Downloading Data](#downloading-data).

### 4. Install the frontend

```bash
cd frontend
npm install
cd ..
```

### 5. Run it (two terminals)

```bash
# Terminal 1 — backend API on http://localhost:8000 (from the repo root, venv active)
uvicorn app.main:app --reload

# Terminal 2 — frontend on http://localhost:5173
cd frontend
npm run dev
```

Open **http://localhost:5173** (not :8000 — the backend only serves the API).
The backend log should show `Loaded dataset: hirise_gale (kind=real_hirise)`.

### 6. Check everything works

```bash
pytest tests/ -q        # expected: 110 passed
```

### Troubleshooting

| Problem | Fix |
|---|---|
| `Port 5173 is already in use` | Another `npm run dev` is still running — close it, or open the URL it printed. |
| Page is blank / `GET /src/main.tsx 404` | You opened :8000. Use http://localhost:5173. |
| "Backend not reachable at localhost:8000" | Start the backend (step 5, terminal 1). |
| Only `synthetic_demo` loads, no `hirise_gale` | Step 3 did not finish — re-run the `hf download` command. |
| HiRISE photo layer shows old tiles | Hard-refresh the browser (Ctrl+F5). |

No data download at all? `python scripts/make_synthetic_demo.py` builds a small
**synthetic** terrain so the app starts (not real Mars data; some tests skip).

For a step-by-step Windows walkthrough see **BEGINNER_SETUP.md**.

---

## Data

**Dataset:** [huggingface.co/datasets/irhabatool/cosmic-trail-data](https://huggingface.co/datasets/irhabatool/cosmic-trail-data)

COSMIC TRAIL's data comes from two places:

- **Processed data (hosted on Hugging Face, about 236 MB).** The Gale Crater
  analysis grids (`analysis.npz`), the elevation, slope and hillshade images,
  `terrain_context.npz` (MOLA heights for the 3D globe), the HiRISE photo mosaic
  (`hirise_gale/ortho_mosaic.tif`, five HiRISE orthoimages merged and clipped to the
  study area at 1 m), the synthetic demo dataset, and the GeoJSON overlays (route,
  hazard zones, geologic units) plus the minerals file. All derived from public
  NASA/USGS products.
- **Raw source files (about 9.5 GB).** The HiRISE DTMs (`DTEEC_*.IMG`), the HiRISE
  orthoimages (`*_ORTHO.JP2`), the MSL Gale 1 m DEM mosaic and the MOLA global DEM.
  Mirrored in the same dataset under `hirise_gale/raw/`; original archives are listed
  in [DATA_SOURCES.md](DATA_SOURCES.md). Only needed to regenerate the processed data.

### Downloading Data

Processed data only (enough to run the app, about 236 MB):

```bash
hf download irhabatool/cosmic-trail-data --repo-type=dataset --local-dir data --exclude "hirise_gale/raw/*"
```

Everything, including raw source files (about 9.7 GB):

```bash
hf download irhabatool/cosmic-trail-data --repo-type=dataset --local-dir data
```

To rebuild the photo mosaic from the raw orthoimages:

```bash
python scripts/build_ortho_mosaic.py
```

---

## Real NASA Data

COSMIC TRAIL can process real HiRISE DTM data.  
Run the downloader/processor:

```bash
python scripts/prepare_data.py
```

That script will try to download the HiRISE product automatically.  
If it cannot reach the server (requires an internet connection), it prints
step-by-step manual download instructions.

See **DATA_SOURCES.md** for the full list of NASA/USGS data products used.

---

## Features

| Feature | Description |
|---------|-------------|
| **A\* routing** | Shortest-path and terrain-weighted path (Horn slope, 8-connected grid) |
| **Terrain layers** | Hillshade / elevation / slope visualisations |
| **Science cards** | Curated facts about Gale Crater sites with peer-reviewed citations |
| **Mission Guide** | Rule-based keyword lookup — NOT an AI, NOT generative text |
| **ARIA assistant** | Floating chat (🤖 ARIA) that answers slope, elevation, hazard, route, distance, minerals and weather questions from the loaded data (`app/assistant.py`). Rule-based and offline — no language model; every reply names its data source |
| **Saved plans** | SQLite-backed plan storage with GeoJSON and briefing export |
| **Provenance panel** | Full data lineage, checksums, and honesty warnings |
| **3D globe** | CesiumJS Mars globe with real terrain (HiRISE/USGS 5 m in the routing area, MOLA elsewhere) and a 1×–5× vertical-exaggeration slider |
| **Minerals layer** | 2 417 aqueous-mineral detection sites (Ehlmann & Edwards 2014; CRISM/OMEGA/THEMIS via NASA Mars Trek), bundled locally — sites, not a mineral map |
| **Place names** | 2 055 official IAU/USGS Gazetteer names, bundled locally, decluttered by zoom and hidden behind terrain |
| **Offline** | Backend, terrain, labels and routing work offline; only the Mars colour basemap (NASA Mars Trek tiles) needs internet |

---

## Honesty Commitments

- Synthetic data is **always** clearly labelled — it is never mixed with or
  presented as real NASA data.
- Slope thresholds are sourced from Apollo EVA traverse data (15° max,
  EPSC2024) and the NASA MSL Engineering User Guide (10° caution).
- Mineral evidence for water/habitability is presented with peer-reviewed
  caveats — COSMIC TRAIL never claims certainty.
- SHA-256 checksums confirm file integrity only; they do not prove NASA
  provenance.
- Mission Guide is explicitly NOT AI and NOT generative text.

See **SCIENTIFIC_LIMITATIONS.md** for the full list of limitations.

---

## Project Structure

```
cosmic-trail/
├── app/                  Python backend (FastAPI)
│   ├── geo.py            Mars sphere geometry, local equidistant cylindrical CRS
│   ├── terrain.py        TerrainDataset, Horn slope, Grid
│   ├── routing.py        A* path-finding, route metrics, comparison
│   ├── science.py        Science cards, Mission Guide rules
│   ├── db.py             SQLite plan storage, GeoJSON/briefing export
│   ├── terrain_tiles.py  Height tiles for the 3D globe (5 m grid + MOLA context)
│   ├── ortho_tiles.py    HiRISE photo mosaic → imagery tiles for the globe
│   ├── assistant.py      ARIA rule-based assistant (POST /api/assistant/chat)
│   └── main.py           FastAPI app, all API endpoints
├── data/                 NOT in Git — download from Hugging Face (see Quick Start)
│   ├── hirise_gale/      Real Gale Crater terrain grids + ortho_mosaic.tif (+ raw/ sources)
│   ├── synthetic_demo/   Generated demo terrain (NOT real Mars data)
│   └── terrain_context.npz  MOLA heights for the 3D globe (build_terrain_context.py)
├── frontend/             React + TypeScript + Vite + CesiumJS app (see frontend/README.md)
│   ├── src/              Globe, route panel, elevation chart, layer controls
│   ├── legacy/           Previous OpenLayers single-page app
│   └── static/ol/        OpenLayers 10.11.0 (used by legacy page and tests)
├── scripts/
│   ├── make_synthetic_demo.py   Generate synthetic demo terrain
│   ├── prepare_data.py          Download + process real HiRISE data
│   ├── build_ortho_mosaic.py    Merge + clip HiRISE orthoimages into the photo mosaic
│   ├── build_terrain_context.py MOLA heights for the 3D globe
│   ├── build_mineral_points.py  Aqueous-mineral detection sites (minerals layer)
│   └── build_mars_labels.py     IAU/USGS place names for the globe
└── tests/
    ├── test_core.py      Core unit tests
    ├── test_api.py       API tests (incl. 3D terrain tiles, minerals)
    └── test_assistant.py ARIA assistant tests
```

---

## Running Tests

```bash
pytest tests/ -v
```

Expected output: **110 passed** with the Hugging Face data in `data/` (some API tests
skip if the real HiRISE dataset or `data/terrain_context.npz` is missing).

---

## License

COSMIC TRAIL code: MIT License (see LICENSE).  
OpenLayers 10.11.0: BSD-2-Clause (see `frontend/static/ol/LICENSE.md`).  
NASA/USGS data: public domain with credit — see DATA_SOURCES.md.

---

## AI Usage Disclosure

See **AI_USAGE.md** for a full account of which parts of this project were
AI-assisted.
