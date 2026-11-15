# COSMIC TRAIL — Data Sources

## Overview

COSMIC TRAIL is designed to work with real NASA/USGS data products.
Because those data files are large and require a live internet connection to
download, COSMIC TRAIL ships with a **synthetic demo dataset** that lets
you explore all features without downloading anything.

The synthetic dataset is **clearly labelled** at every level and is **never**
mixed with or presented as real data.

---

## NASA Space Apps Challenge — Official Resources Used

| Resource | URL | How COSMIC TRAIL Uses It |
|----------|-----|--------------------------|
| Mars Trek | [trek.nasa.gov/mars](https://trek.nasa.gov/mars) | Map tile imagery for 3D Mars globe |
| USGS Planetary Mapping | [astrogeology-usgs.hub.arcgis.com](https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars) | Geologic unit polygons for Gale Crater |
| Curiosity Proposed Path | [science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp](https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/) | Reference traverse overlay on map |
| NASA Worldview | [worldview.earthdata.nasa.gov](https://worldview.earthdata.nasa.gov/) | Dust storm hazard context |
| Perseverance Raw Images | [mars.nasa.gov/mars2020/multimedia/raw-images](https://mars.nasa.gov/mars2020/multimedia/raw-images/) | Surface imagery science context |

### Mars Trek — WMTS basemap tiles

The 3D globe's colour basemap is the Viking MDIM 2.1 colour mosaic (232 m/px) served
by NASA Mars Trek as WMTS tiles (no token). URL template used in
`frontend/src/components/Globe.tsx`:

```
https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg
```

Geographic tiling scheme (2×1 tiles at level 0, starting at −180°), planetocentric,
east-positive, `maximumLevel` 7. Tiles need an internet connection; offline the globe
shows its plain base colour. The map shows a clickable credit
"🛰️ Map imagery: NASA Mars Trek | trek.nasa.gov/mars" at its bottom-right.

### USGS geologic units — `data/usgs_geologic_units.geojson`

Two units from the Geologic Map of Mars (Tanaka et al. 2014, USGS Scientific
Investigations Map 3292) for the study area (lon 137.30–137.60°E, lat 4.35–4.85°S):
**eHt** (Early Hesperian Transition, crater floor) and **Htu** (Hesperian transition
undivided unit, Hesperian ~3.2–3.7 Ga, Mount Sharp layered deposits). Served by
`GET /api/geology/units`; toggled with the **Geologic Units** layer.

The Htu assignment is stated in the SIM 3292 pamphlet (Hesperian Period section):
"Acidic weathering conditions during the Hesperian led to sulfate enrichment of
layered deposits in Valles Marineris and Gale crater (Hesperian transition undivided
unit, Htu)". The pamphlet's crater table dates Gale itself as Early Hesperian (eH).
Hesperian age range is the pamphlet's Table 1 epoch boundaries (Michael 2013:
~3.24–3.56 Ga Hartmann, ~3.37–3.71 Ga Neukum). The pamphlet does not explicitly map
the Gale floor as eHt; that assignment is unverified.

> **Caveat:** the polygons are simplified rectangles, not contacts digitized from
> SIM 3292. That map is 1:20,000,000 scale, so unit boundaries at this zoom are
> uncertain by kilometres. Display/education only.

### Curiosity's Proposed Path — `data/curiosity_official_route.geojson`

LineString with six waypoints (Bradbury Landing, Yellowknife Bay, Pahrump Hills,
Murray Buttes, Hematite Ridge, Clay-bearing Unit), referencing NASA JPL's
[Curiosity's Proposed Path up Mount Sharp](https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/).
Served by `GET /api/curiosity/route`; drawn as a dashed gold line with clickable
waypoints and a science card (`curiosity_official_route`).

> **Caveat:** waypoint positions are approximate (only Bradbury Landing is a
> published coordinate); they were not measured from the NASA map or from the
> rover's traverse data.

### Published weather figures for ARIA — `app/weather_facts.py`

ARIA's weather answers use **published figures only**, each cited in the file (no REMS/RAD data product
is loaded and nothing is live):

| Figure | Value | Source |
|--------|-------|--------|
| Air temperature, daily high / low | about 0 °C / about −70 °C (mid-Aug 2012 – late Feb 2013) | [NASA/JPL PIA16913](https://www.jpl.nasa.gov/images/pia16913-steady-temperatures-at-mars-gale-crater/), REMS on Curiosity |
| Radiation | about 0.64 mSv/day | Hassler et al. 2014 (RAD) |

> **Caveat:** these describe one period near the landing site, not a forecast and not the whole Mars year.
> To use the full REMS record instead, download the reduced MOD RDR files from the PDS Atmospheres Node
> (https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html) and summarise them in a script.

### NASA Worldview — dust storm context

Worldview tracks dust on Earth, not Mars; it is cited as the reference for the
`dust_storms` science card, together with MARCI (MRO) Mars weather reports and the
2018 (MY34) global dust storm literature. Mission Guide keywords: *dust, storm,
weather*. **No real-time Mars weather data is used.**

### Perseverance / Curiosity raw images — imagery context

Cited by the `surface_imagery_context` science card (Mission Guide keywords:
*image, photo, picture, visual, camera*). The Gale Crater and Curiosity waypoint
info cards have a **📷 View Curiosity Images (NASA)** button linking to
https://mars.nasa.gov/msl/multimedia/raw-images/. **No rover images are loaded by the app.**

---

### Location context for ARIA and the route panel — `app/context.py`

ARIA's "Is this safe?", "What's here?" and "Best path to clay?" answers, and the route
panel's 🔬 / 🌡️ / 📡 lines, are computed from data already in the app:

| Check | Data |
|-------|------|
| Geologic unit at a point | `data/usgs_geologic_units.geojson` (simplified SIM 3292 rectangles) |
| Nearest orbital mineral detection | `data/minerals/aqueous_minerals.json` (Ehlmann & Edwards 2014) |
| Nearest confirmed clay | Yellowknife Bay, approx. 137.4453°E 4.5890°S (Vaniman et al. 2014; Grotzinger et al. 2014) |
| HiRISE vs gap fill | the analysis grid's `usgs_filled` / `mola_filled` masks |
| Dune sand (thermal / footing) | `data/hazard_zones.geojson` — approximate Bagnold Dunes outline |

> **Dunes:** the Bagnold Dunes polygon (137.38–137.52°E, 4.65–4.72°S) is an approximate
> outline from NASA Mars Trek and Curiosity traverse papers (cited: Bridges et al. 2017, JGR Planets), not a
> mapped dune boundary. Treat dune warnings near its edges as indicative. More outlines can be
> added with `{"kind": "dune", "name": ..., "source": ...}` (see the file's `how_to_add`);
> restart the backend to load them.

### Place names ARIA accepts as a position — `app/aria_places.py`

When a user names a place ("it's near Pahrump Hills"), ARIA uses that place's coordinates instead of the
map centre. **No coordinates were added for this**; every position comes from a file listed above:

| Places | Coordinates from | Precision |
|--------|------------------|-----------|
| Bradbury Landing, Aeolis Mons (Mount Sharp), Aeolis Palus | science cards in `app/science.py` (cited there) | Bradbury Landing published; the others approximate |
| Yellowknife Bay | `app/context.py` (Vaniman et al. 2014; Grotzinger et al. 2014) | approximate |
| Pahrump Hills, Murray Buttes, Hematite Ridge, Clay-bearing Unit | `data/curiosity_official_route.geojson` waypoints ([NASA JPL proposed path](https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/)) | **approximate** (see the caveat above) |
| Any IAU-named Mars feature (e.g. Olympus Mons, Jezero Crater) | `frontend/src/data/mars_labels.json` ([IAU/USGS Gazetteer of Planetary Nomenclature](https://planetarynames.wr.usgs.gov/GIS_Downloads)) | feature centre point |

ARIA's reply names the place, its coordinates, says "approximate" where that applies, and cites the
coordinate source in its Source line. Names that are not in this list get "I don't have 'X' in my place
list" — ARIA never estimates a position. To make Pahrump Hills (or another waypoint) precise, replace its
waypoint in the GeoJSON with a position measured from a cited NASA/JPL or USGS product and cite it here.

## NASA Data Products Used / Referenced

### Primary: HiRISE Digital Terrain Model (DTM)

| Field | Value |
|-------|-------|
| Product ID | `DTEEC_024234_1755_024300_1755_U01` |
| Instrument | HiRISE (High Resolution Imaging Science Experiment) |
| Spacecraft | Mars Reconnaissance Orbiter |
| PI | Alfred McEwen, University of Arizona |
| Resolution | ~1 m/post raw; resampled to 5 m for routing |
| Coverage | Gale Crater floor, Bradbury Landing area (~137.35–137.55°E, ~−4.75–−4.45°) |
| File size | ~444 MB (.IMG format) |
| Format | PDS-labelled VICAR binary (big-endian float32) |
| Source URL | https://www.uahirise.org/PDS/DTM/ESP/ORB_024200_024299/ESP_024234_1755_ESP_024300_1755/ |
| Credit | NASA/JPL/University of Arizona |
| Terms | NASA public-domain data. Credit: NASA/JPL/University of Arizona. |
| Coordinate system | Mars IAU 2000 sphere (R = 3,396,190 m), planetocentric lat, lon positive east |
| Known artifacts | Jitter artefacts possible at orbit boundaries; no-data patches where correlation failed |

### HiRISE Orthoimage (context imagery)

| Field | Value |
|-------|-------|
| Product ID | `ESP_024234_1755_RED_C_01_ORTHO.JP2` |
| Format | JP2 (JPEG 2000) |
| Source URL | Same directory as the DTM above |
| Use | Background context layer (not currently loaded in prototype; planned) |

### HiRISE photo layer — `data/hirise_gale/ortho_mosaic*.tif`

Built by `scripts/build_ortho_mosaic.py` from the orthoimages that accompany the five HiRISE DTM
pairs over the study window (`https://www.uahirise.org/PDS/DTM/…`, NASA/JPL-Caltech/UArizona).
Served as a 256 px tile pyramid (`app/ortho_tiles.py`) down to the mosaic's native resolution.

| Mosaic | Source product | Download | Mosaic size | Status |
|--------|----------------|----------|-------------|--------|
| `ortho_mosaic.tif` (1 m/px) | `*_RED_C_01_ORTHO.JP2` (1.01 m/px) | ~178 MB | 144 MB | default, distributed |
| `ortho_mosaic_50cm.tif` (0.5 m/px) | `*_RED_A_01_ORTHO.JP2` (0.25 m/px, box-averaged to 0.5 m) | ~2.23 GB | ~0.6–0.8 GB (est.) | optional: `prepare_data.py --ortho-res 0.5` |
| `ortho_mosaic_25cm.tif` (0.25 m/px) | `*_RED_A_01_ORTHO.JP2` (native) | ~2.23 GB | ~2–3 GB (est.) | optional: `--ortho-res 0.25` |

The backend serves the sharpest mosaic present; where a finer mosaic has no data (for example a
partial download) tiles are filled from the 1 m mosaic. Every mosaic is lossless (DEFLATE), and the
pixels are only resampled (box average when making pixels coarser), never sharpened or upscaled. The
same fixed tone curve (half histogram equalisation, `app/ortho_tiles.py`) is applied to every
tile for legibility, because raw HiRISE RED values sit in a narrow band.

### Context: MOLA Global Topography

| Field | Value |
|-------|-------|
| Product | MOLA 463 m/pixel global mosaic (MEGDR) |
| Instrument | MOLA (Mars Orbiter Laser Altimeter) |
| Spacecraft | Mars Global Surveyor |
| Resolution | 463 m/pixel |
| File size | ~2 GB |
| Source | https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/ |
| Use | COSMIC TRAIL uses MOLA-derived Gale Crater elevation range (−4,500 m to −4,200 m basin floor) for synthetic terrain calibration |
| Credit | NASA/JPL/GSFC |

### Science Card Sources (peer-reviewed literature)

The science cards cite the following publications (accessed via published
papers; COSMIC TRAIL does not reproduce paper text):

- Grotzinger et al. (2014) "A Habitable Fluvio-Lacustrine Environment at
  Yellowknife Bay, Gale Crater, Mars." *Science* 343, 1242777.
  https://doi.org/10.1126/science.1242777

- Grotzinger et al. (2015) "Deposition, exhumation, and paleoclimate of an
  ancient lake deposit, Gale Crater, Mars." *Science* 350, aac7575.
  https://doi.org/10.1126/science.aac7575

- Milliken et al. (2010) "Paleoclimate of Mars as captured by the
  stratigraphic record in Gale Crater." *Geophysical Research Letters* 37.
  https://doi.org/10.1029/2009GL041870

- Murchie et al. (2009) "A synthesis of Martian aqueous mineralogy after 1
  Mars year of observations from the Mars Reconnaissance Orbiter."
  *JGR Planets* 114.

---

## Synthetic Demo Dataset

The synthetic dataset is generated by `scripts/make_synthetic_demo.py` using:

- A fixed numpy random seed (42) for reproducibility
- An elevation base of −4,500 m (consistent with MOLA basin-floor data)
- Procedural noise amplitude tuned to produce walkable slopes (p95 ≈ 14°)
- Two artificial NoData patches to test UI handling
- Grid: 2000 × 2000 cells at 5 m/cell = 10 km × 10 km

The synthetic dataset:
- Contains **no real sensor measurements**
- Is stored only in `data/synthetic_demo/`
- Is **never** loaded if real HiRISE data is present
- Carries the disclaimer `"SYNTHETIC DATA — NOT REAL TERRAIN"` in every output file

---

## How to Download Real Data Manually

If `scripts/prepare_data.py` cannot reach the HiRISE server, download these
files manually:

1. HiRISE DTM (444 MB):  
   https://www.uahirise.org/PDS/DTM/ESP/ORB_024200_024299/ESP_024234_1755_ESP_024300_1755/DTEEC_024234_1755_024300_1755_U01.IMG

2. HiRISE Ortho (27 MB):  
   https://www.uahirise.org/PDS/DTM/ESP/ORB_024200_024299/ESP_024234_1755_ESP_024300_1755/ESP_024234_1755_RED_C_01_ORTHO.JP2

3. Place both files in `data/raw/`

4. Run:
   ```
   python scripts/prepare_data.py
   ```
   The script will detect the existing files and skip the download step.

---

## OpenLayers

| Field | Value |
|-------|-------|
| Library | OpenLayers 10.11.0 |
| License | BSD-2-Clause |
| Bundled at | `frontend/static/ol/` |
| Source | https://github.com/openlayers/openlayers |
| Why bundled | The app must work **fully offline** — no CDN |

---

## Coordinate Reference System

COSMIC TRAIL uses a **local equidistant cylindrical projection** centred on
Bradbury Landing (137.4417°E, −4.5895°):

```
x = R · cos(lat₀) · Δlon_rad
y = R · Δlat_rad
R = 3,396,190 m  (Mars MOLA sphere radius)
```

This is an approximation valid within the 10 km study window.  
Scale error at the grid boundary is < 0.05%.  
All distances reported are planimetric in this local projection, plus a
geodesic (Mars-sphere Haversine) distance for reference.

Latitude is **planetocentric** (consistent with HiRISE PDS labels).  
Longitude is **positive east**.

---

## Data Integrity

SHA-256 checksums are computed for all generated files and stored in
`metadata.json`. These checksums:
- Confirm that the files have not been corrupted or altered
- Do **not** prove NASA provenance (the checksums cover the processed files,
  not the original PDS products)

The provenance panel in the app displays all checksums and states this
limitation explicitly.
