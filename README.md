# COSMIC TRAIL: plan a walk on Mars

**Team cosmiCore · NASA Space Apps Challenge 2026**
Challenge: *Interplanetary Survival Guide: Martian Map*

COSMIC TRAIL is a route planner for Gale Crater, where NASA's Curiosity rover landed. You pick a
start and a destination on a 3D Mars globe, and we work out two walking routes from real HiRISE
elevation data: the shortest one, and one that stays on gentle ground. Along the way you can look
at the terrain, check slopes, read about the science sites nearby, and ask ARIA, our offline
assistant, questions about the area.

It's a learning and demo tool. It is not certified for real missions or rover driving.

---

## What it does

- **Two routes, side by side.** An A* search finds the *shortest* route and a *terrain-safe* route
  that avoids steep and uphill ground. Neither route ever crosses a slope over 15°, and stretches
  between 10° and 15° are flagged. A comparison table shows the trade-off in distance, climb and
  slope.
- **Fast routing.** The A* search is compiled with numba, so even routes across the whole study area
  take about 1–5 seconds, depending on the laptop. Routes longer than 3 km may use a corridor
  search: a coarse 20 m route first, then a full-resolution search inside a corridor around it. The
  result stays close to the true optimum (our tests require it to be within 2%), and each route
  says which search it used.
- **Elevation profile.** A chart under the map shows height along the route, coloured by slope. You
  can resize it by dragging its edges, and export the route as GeoJSON or as a plain-text briefing.
- **3D globe.** A full-screen Mars globe (CesiumJS) with frosted-glass panels on top. Gale Crater
  uses our 5 m terrain grid, and the rest of Mars uses MOLA heights. A *Whole Mars* view shows
  MOLA colour relief and NASA's landing sites.
- **Layers.** HiRISE terrain (hillshade, elevation or slope), the HiRISE photo, the routable area,
  aqueous-mineral detection sites, USGS geologic units, NASA's proposed Curiosity path, science
  sites and IAU place names. Labels sit beside their markers and never overlap.
- **Sharp HiRISE photo.** The photo layer streams as map tiles down to its native 1 m/px. The camera
  stops zooming where the photo would only get blurrier, and a small chip says when you're at full
  detail. A scale bar shows distances in metres. If you have the disk space, an optional 0.5 m
  version can be built from the full-resolution HiRISE images (see
  [DATA_SOURCES.md](DATA_SOURCES.md)).
- **ARIA, the offline assistant.** ARIA answers questions about slopes, safe directions,
  temperatures, sunlight, radiation, your route, minerals and science sites. It understands
  follow-ups ("and at night?", "what about south?"), typos and place names ("it's near Pahrump
  Hills"). It checks slope in any compass direction from the real grid, and ends every answer with
  its sources. ARIA is rule-based and runs entirely on your machine: no language model, no API, no
  internet.
- **Honest weather.** Temperatures and radiation are published historical figures from Curiosity
  (REMS, RAD), always shown with their source. They are not live readings or a forecast.

## The data

| Data | Source | How we use it |
|------|--------|---------------|
| Terrain | 5 HiRISE DTMs (NASA/JPL/UArizona), gaps filled from the USGS MSL Gale DEM | 5 m routing grid: 88.2% HiRISE, 11.8% USGS fill |
| Photo | HiRISE RED orthoimages | Photo layer (1 m/px, optional 0.5 m) |
| Global relief | MOLA 463 m DEM | 3D globe outside the study area |
| Basemap | [NASA Mars Trek](https://trek.nasa.gov/mars) tiles (Viking MDIM 2.1, MOLA shaded relief) | Globe imagery (the only part that needs internet) |
| Minerals | Ehlmann & Edwards (2014), via Mars Trek | 2,417 detection sites |
| Geology | Tanaka et al. (2014), USGS SIM 3292 | Two simplified units for the study area |
| Curiosity path | [NASA JPL proposed path up Mount Sharp](https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/) | Reference overlay (approximate waypoints) |

Every product ID, citation and caveat is in [DATA_SOURCES.md](DATA_SOURCES.md).

---

## Quick start (Windows)

You need **Git**, **Python 3.11–3.14** and **Node.js 22+**. The code is on GitHub. The data
(about 236 MB) is on [Hugging Face](https://huggingface.co/datasets/irhabatool/cosmic-trail-data)
because it's too big for Git. Run these in **PowerShell**:

```powershell
# 1. Get the code
git clone https://github.com/IB-Mustafa/Cosmic_Trail_A_Mars_Map.git
cd Cosmic_Trail_A_Mars_Map

# 2. Python packages (FastAPI, rasterio, numba, ...)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Data from Hugging Face (the terrain grid is checksum-verified)
python scripts/download_data.py

# 4. Frontend packages, and tell the frontend where the backend is
cd frontend
npm install
Set-Content -Path .env.local -Value "VITE_API_BASE=http://127.0.0.1:8000" -Encoding ascii
cd ..
```

Then start the app in **two terminals**:

```powershell
# Terminal 1, in the repo folder with the venv active: the backend
$env:PYTHONUTF8 = "1"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: the frontend
cd frontend
npm run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173**. The first route can take a few seconds while numba compiles the
search; after that it's fast.

On macOS or Linux, activate the venv with `source .venv/bin/activate` and skip the `PYTHONUTF8`
line. If something doesn't work, [LOCAL_SETUP.md](LOCAL_SETUP.md) walks through every step with
checks and fixes for common problems.

## Try it

1. Open **Gale study area** and click **Find Route**. A and B start near Bradbury Landing.
2. Compare the solid pink terrain-safe route with the dashed red shortest route, and look at the
   elevation profile below the map.
3. Press **Pick** to move A or B anywhere inside the dashed routable area.
4. Turn on **HiRISE photo** and zoom in until the "Max HiRISE detail" chip appears.
5. Open **ARIA** and ask "Am I safe here?", then "it's near Pahrump Hills", or "is it safe to go
   north?".
6. Switch to **Whole Mars** to see the landing sites, then click the Gale Crater marker to come back.

## Tests

```powershell
python -m pytest
```

With the data downloaded, there are 197 tests. One of them checks that a long route takes under
2 seconds. On slower laptops it can take about 4–5 seconds and fail, even though the route itself
is correct.

## More about the project

| Document | What's in it |
|----------|--------------|
| [LOCAL_SETUP.md](LOCAL_SETUP.md) | Full setup for Windows, macOS and Linux, with troubleshooting |
| [BEGINNER_SETUP.md](BEGINNER_SETUP.md) | The same setup for complete beginners on Windows |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the backend, frontend and data fit together |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Every dataset, product ID, citation and link |
| [SCIENTIFIC_LIMITATIONS.md](SCIENTIFIC_LIMITATIONS.md) | What the data and the routes can and can't tell you |
| [JUDGING_EVIDENCE.md](JUDGING_EVIDENCE.md) | Our data check: what is static, live or calculated, plus test results |
| [MISSION_LOG.md](MISSION_LOG.md) | How we built it, and our AI tools disclosure |
| [frontend/README.md](frontend/README.md) | Notes on the frontend code |

## AI tools

We used AI coding assistants while building COSMIC TRAIL. ARIA itself uses no AI at runtime. The
full disclosure is in [MISSION_LOG.md](MISSION_LOG.md).

## Credits

HiRISE data and images: NASA/JPL/University of Arizona. USGS MSL Gale DEM, geologic map and
planetary nomenclature: USGS Astrogeology Science Center. MOLA: NASA GSFC / MGS MOLA Science Team.
Map tiles: NASA Mars Trek. Mineral sites: Ehlmann & Edwards (2014). Temperatures: NASA/JPL
PIA16913 (REMS). Radiation: Hassler et al. (2014) (RAD).
