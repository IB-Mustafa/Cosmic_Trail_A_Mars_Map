# Where our data comes from

This page lists every dataset, image service and paper COSMIC TRAIL uses, what we did with it, and
how far you can trust it. We checked every link and citation below before submitting.

The processed data is about 236 MB and lives on Hugging Face
([irhabatool/cosmic-trail-data](https://huggingface.co/datasets/irhabatool/cosmic-trail-data)),
not in Git. `python scripts/download_data.py` fetches it and checks the terrain grid against the
SHA-256 recorded in its metadata. To rebuild it from the original NASA and USGS files, run `scripts/prepare_data.py` (see
the end of this page).

---

## NASA Space Apps resources

| Resource | Link | How we use it |
|----------|------|---------------|
| NASA Mars Trek | [trek.nasa.gov/mars](https://trek.nasa.gov/mars) | Basemap tiles for the globe, and the mineral detection layer |
| USGS planetary mapping | [astrogeology-usgs.hub.arcgis.com](https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars) | Geologic units for Gale Crater |
| Curiosity's proposed path | [science.nasa.gov](https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/) | Reference path overlay |
| NASA Worldview | [worldview.earthdata.nasa.gov](https://worldview.earthdata.nasa.gov/) | Cited on the dust storm card (it tracks Earth, so there's no Mars data from it) |
| Rover raw images | [Perseverance](https://mars.nasa.gov/mars2020/multimedia/raw-images/), [Curiosity](https://mars.nasa.gov/msl/multimedia/raw-images/) | Linked from the info cards; no images are loaded into the app |

---

## Terrain: HiRISE DTMs with a USGS gap fill

The routing grid merges five HiRISE stereo DTMs (NASA/JPL/University of Arizona, about 1 m post
spacing) that overlap our study window:

| DTM | HiRISE page |
|-----|-------------|
| `DTEEC_018854_1755_018920_1755_U01` (covers Bradbury Landing) | [uahirise.org/dtm/ESP_018854_1755](https://www.uahirise.org/dtm/ESP_018854_1755) |
| `DTEEC_023957_1755_024023_1755_U01` | [uahirise.org/dtm/ESP_023957_1755](https://www.uahirise.org/dtm/ESP_023957_1755) |
| `DTEEC_009505_1755_009571_1755_U01` | [uahirise.org/dtm/PSP_009505_1755](https://www.uahirise.org/dtm/PSP_009505_1755) |
| `DTEEC_010573_1755_010639_1755_U01` | [uahirise.org/dtm/PSP_010573_1755](https://www.uahirise.org/dtm/PSP_010573_1755) |
| `DTEEC_040770_1755_039280_1755_U01` | [uahirise.org/dtm/ESP_040770_1755](https://www.uahirise.org/dtm/ESP_040770_1755) |

The files themselves are under `https://www.uahirise.org/PDS/DTM/` (the exact folders are listed in
`scripts/prepare_data.py`). We also tried `DTEEC_024234_1755_024300_1755_U01` and
`DTEEC_001488_1750_001752_1750_U02`, but neither has valid data inside the window, so we skipped
them. Usage terms: [uahirise.org/media/usage.php](https://uahirise.org/media/usage.php). The data is
public domain, and the credit is NASA/JPL/University of Arizona.

Where no HiRISE DTM has data, we fill the gaps from the **USGS MSL Gale Merged DEM 1 m v3**
(HiRISE + CTX + HRSC, tied to MOLA; USGS Astrogeology Science Center):
[product page](https://astrogeology.usgs.gov/search/map/mars_msl_gale_merged_dem_1m) ·
[`MSL_Gale_DEM_Mosaic_1m_v3.tif`](https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif).

From `data/hirise_gale/metadata.json`:

| | Value |
|---|---|
| Study window | 137.35–137.55°E, 4.75–4.45°S |
| Grid | 2,364 × 3,558 cells at 5 m (8,411,112 cells) |
| Valid cells | 8,399,272 (99.86%) |
| From HiRISE | 7,417,993 (88.19%) |
| From the USGS fill | 993,119 (11.81%) |
| From MOLA | 0 |
| Slope, 95th percentile | 18.81° (Horn 1981, 3×3) |

Each 1 m DEM is resampled to 5 m. The USGS heights are shifted to meet the HiRISE surface (see
[SCIENTIFIC_LIMITATIONS.md](SCIENTIFIC_LIMITATIONS.md)). The `usgs_filled` mask in `analysis.npz`
records which cells came from USGS, and the hover bar shows the source under the cursor.

## HiRISE photo layer: `data/hirise_gale/ortho_mosaic*.tif`

`scripts/build_ortho_mosaic.py` merges the orthoimages that belong to the same five DTM pairs. The
first image in its list wins where they overlap, each strip is histogram-matched to the others,
and the result is clipped to the study window. The mosaic covers 88.17% of the window. The backend
serves it as a 256 px tile pyramid (`app/ortho_tiles.py`) down to its native resolution.

| Mosaic | Source product | Download | Mosaic size | Status |
|--------|----------------|----------|-------------|--------|
| `ortho_mosaic.tif` (1 m/px) | `*_RED_C_01_ORTHO.JP2` (1.01 m/px) | ~178 MB | 144 MB | Default, on Hugging Face |
| `ortho_mosaic_50cm.tif` (0.5 m/px) | `*_RED_A_01_ORTHO.JP2` (0.25 m/px, box-averaged to 0.5 m) | ~2.23 GB | ~0.6–0.8 GB (estimate) | Optional: `prepare_data.py --ortho-res 0.5` |
| `ortho_mosaic_25cm.tif` (0.25 m/px) | `*_RED_A_01_ORTHO.JP2` (native) | ~2.23 GB | ~2–3 GB (estimate) | Optional: `--ortho-res 0.25` |

The backend serves the sharpest mosaic it finds, and fills any part it doesn't cover from the 1 m
mosaic. All mosaics are lossless (DEFLATE).

**The HiRISE photo is shown with a fixed contrast stretch (half histogram equalisation) for
legibility; no sharpening or upscaling.** Raw HiRISE RED values sit in a narrow band (about 178–223
out of 255), so without the stretch the photo looks flat grey. The same curve is used for every
tile.

## Global relief: MOLA

The **MGS MOLA DEM 463 m** global mosaic (NASA GSFC MOLA Science Team / USGS; Smith et al. 2001):
[product page](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m) ·
[`Mars_MGS_MOLA_DEM_mosaic_global_463m.tif`](https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif)
(about 2 GB). `scripts/build_terrain_context.py` turns it into `data/terrain_context.npz`, which
gives the 3D globe its heights outside the study area: 463 m around Gale, and averaged to 1/8°
elsewhere. ARIA uses it for rough heights outside the grid, and `prepare_data.py` falls back to it
for gap filling if the USGS DEM is missing. The underlying PDS product (MEGDR) is at
[pds-geosciences.wustl.edu](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/).

## Basemap tiles: NASA Mars Trek

The globe's colour basemap is the **Viking MDIM 2.1 colour mosaic** (232 m/px). The Whole Mars view
adds **MGS MOLA colour-shaded relief** (463 m/px). Both are WMTS tiles from NASA Mars Trek, with no
token:

```
https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg
https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg
```

They use geographic tiling (2×1 tiles at level 0, starting at −180°). Level 7 is the deepest level
Mars Trek serves for both layers, and that's what we use. These tiles are the only thing that
needs internet. Offline, the globe shows a plain colour and everything else still works. A credit
link sits at the bottom-right of the map.

## Minerals: `data/minerals/aqueous_minerals.json`

There are 2,417 aqueous-mineral detection sites from MRO CRISM, Mars Express OMEGA and Mars Odyssey
THEMIS, compiled by **Ehlmann, B. L. & Edwards, C. S. (2014)**, "Mineralogy of the Martian
Surface", *Annual Review of Earth and Planetary Sciences* 42: 291–315,
[doi:10.1146/annurev-earth-060313-055024](https://doi.org/10.1146/annurev-earth-060313-055024).
They're served by NASA Mars Trek as
[Aqueous Mineral Distribution](https://trek.nasa.gov/mars/trekarcgis/rest/services/Aquieous_Mineral_Distribution_Options_clon0/MapServer/0),
and bundled with `scripts/build_mineral_points.py`. Each point marks a detection site, so they
aren't a mineral map.

## Geologic units: `data/usgs_geologic_units.geojson`

There are two units from **Tanaka, K. L. et al. (2014)**, *Geologic Map of Mars*, USGS Scientific
Investigations Map 3292, 1:20,000,000 ([pubs.usgs.gov/sim/3292](https://pubs.usgs.gov/sim/3292/),
[doi:10.3133/sim3292](https://doi.org/10.3133/sim3292)):

- **Htu** (Hesperian transition undivided unit) covers Mount Sharp's layered deposits. The SIM 3292
  pamphlet says: "Acidic weathering conditions during the Hesperian led to sulfate enrichment of
  layered deposits in Valles Marineris and Gale crater (Hesperian transition undivided unit, Htu)".
- **eHt** (Early Hesperian transition) covers the crater floor. The pamphlet dates Gale itself as
  Early Hesperian, but doesn't map the floor as eHt, so that assignment is our own and unverified.

The polygons are simplified rectangles, not digitised map contacts. At 1:20 million, boundaries at
this zoom are uncertain by kilometres, so they're for display and teaching only.

## Curiosity's proposed path: `data/curiosity_official_route.geojson`

This is a line through six waypoints: Bradbury Landing, Yellowknife Bay, Pahrump Hills, Murray
Buttes, Hematite Ridge and the clay-bearing unit. It's based on NASA JPL's
[Curiosity's Proposed Path up Mount Sharp](https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/).
Only Bradbury Landing (4.5895°S, 137.4417°E) is a published coordinate. We placed the other
waypoints by hand, without measuring them from the NASA map or from rover telemetry, so they're
approximate. This isn't the track Curiosity actually drove.

## Dunes: `data/hazard_zones.geojson`

This is an approximate outline of the Bagnold Dunes (137.38–137.52°E, 4.65–4.72°S), drawn from
NASA Mars Trek and Curiosity traverse papers. Reference: **Bridges, N. T. et al. (2017)**, "Martian
aeolian activity at the Bagnold Dunes, Gale Crater: The view from the surface and orbit", *JGR
Planets* 122: 2077–2110, [doi:10.1002/2017JE005263](https://doi.org/10.1002/2017JE005263). It's not
a mapped dune boundary, so treat dune warnings near its edges as hints.

## Place names

There are 2,055 official names from the
[IAU/USGS Gazetteer of Planetary Nomenclature](https://planetarynames.wr.usgs.gov/GIS_Downloads),
bundled in `frontend/src/data/mars_labels.json` by `scripts/build_mars_labels.py`. Each name links
to its gazetteer page (`https://planetarynames.wr.usgs.gov/Feature/{id}`).

ARIA also accepts place names as a position ("it's near Pahrump Hills"). Every coordinate it uses
comes from a file on this page. We didn't add any coordinates for that feature:

| Places | Coordinates from | Precision |
|--------|------------------|-----------|
| Bradbury Landing, Aeolis Mons (Mount Sharp), Aeolis Palus | Science cards in `app/science.py` | Bradbury Landing published, the others approximate |
| Yellowknife Bay | `app/context.py` (Vaniman et al. 2014; Grotzinger et al. 2014) | Approximate |
| Pahrump Hills, Murray Buttes, Hematite Ridge, clay-bearing unit | Curiosity path waypoints | Approximate |
| Any IAU-named feature (e.g. Olympus Mons) | The gazetteer | Feature centre point |

If a name isn't in that list, ARIA says "I don't have 'X' in my place list". It never guesses a
position.

## Weather and environment figures: `app/weather_facts.py`

ARIA only quotes published figures, each with its source. No REMS or RAD data product is loaded,
and nothing is live:

| Figure | Value | Source |
|--------|-------|--------|
| Air temperature, daily high and low | About 0 °C and −70 °C (mid-August 2012 to late February 2013) | NASA/JPL [PIA16913](https://photojournal.jpl.nasa.gov/catalog/PIA16913) "Steady Temperatures at Mars' Gale Crater" (REMS) |
| Radiation | About 0.64 mSv per day | Hassler, D. M. et al. (2014), "Mars' Surface Radiation Environment Measured with the Mars Science Laboratory's Curiosity Rover", *Science* 343, 1244797, [doi:10.1126/science.1244797](https://doi.org/10.1126/science.1244797) (RAD) |
| Sol length, air, general facts | General Mars knowledge | [NASA Mars Fact Sheet (NSSDCA)](https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html) |

These figures describe one period near the landing site. They aren't a forecast, and they don't
cover the whole Mars year. The full REMS record is on the PDS Atmospheres Node
(https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html). The dust
storm card also points to [MSSS MARCI weather reports](https://www.msss.com/msss_images/subject/weather_reports.html)
and to Guzewich, S. D. et al. (2019), *Geophysical Research Letters* 46: 71–79,
[doi:10.1029/2018GL080839](https://doi.org/10.1029/2018GL080839).

## Slope limits

| Limit | Value | Where it comes from |
|-------|-------|---------------------|
| Hard limit (routes never cross it) | 15° | Apollo astronaut experience on slopes: EPSC2024-196, "Astronaut experiences on the slopes along Apollo EVAs" ([abstract](https://meetingorganizer.copernicus.org/EPSC2024/EPSC2024-196.html)). The JPL guide below also classes slopes over 15° as "high slope". |
| Caution (flagged on the route) | 10° | JPL, *MSL Landing Site Selection: User's Guide to Engineering Constraints* ([PDF](https://marsoweb.nas.nasa.gov/landingsites/msl/memoranda/MSL_Eng_User_Guide_v2.pdf)). In loose granular terrain, tilt under 10° gives 0–25% upslope slip, and 10–17° is "transitionary" (25–80% slip). |

These are planning guides from past missions. They haven't been validated for this terrain model
or for future spacesuits.

## Science card references (`app/science.py`)

- Grotzinger, J. P. et al. (2014), "A Habitable Fluvio-Lacustrine Environment at Yellowknife Bay,
  Gale Crater, Mars", *Science* 343, 1242777. [doi:10.1126/science.1242777](https://doi.org/10.1126/science.1242777)
- Vaniman, D. T. et al. (2014), "Mineralogy of a Mudstone at Yellowknife Bay, Gale Crater, Mars",
  *Science* 343, 1243480. [doi:10.1126/science.1243480](https://doi.org/10.1126/science.1243480)
- Ming, D. W. et al. (2014), "Volatile and Organic Compositions of Sedimentary Rocks in Yellowknife
  Bay, Gale Crater, Mars", *Science* 343, 1245267. [doi:10.1126/science.1245267](https://doi.org/10.1126/science.1245267)
- Grotzinger, J. P. et al. (2015), "Deposition, exhumation, and paleoclimate of an ancient lake
  deposit, Gale crater, Mars", *Science* 350, aac7575. [doi:10.1126/science.aac7575](https://doi.org/10.1126/science.aac7575)
- Smith, D. E. et al. (2001), "Mars Orbiter Laser Altimeter: Experiment summary after the first year
  of global mapping of Mars", *JGR Planets* 106: 23689–23722. [doi:10.1029/2000JE001364](https://doi.org/10.1029/2000JE001364)
- Guzewich, S. D. et al. (2019), see the weather section above.
- The Bradbury Landing card takes its coordinates from a secondary source (Wikipedia's "Bradbury
  Landing" article, citing NBC/NASA), and the card says so.

Further reading we used while choosing what to show, but don't cite in the app:

- Milliken, R. E. et al. (2010), "Paleoclimate of Mars as captured by the stratigraphic record in
  Gale Crater", *Geophysical Research Letters* 37. [doi:10.1029/2009GL041870](https://doi.org/10.1029/2009GL041870)
- Murchie, S. L. et al. (2009), "A synthesis of Martian aqueous mineralogy after 1 Mars year of
  observations from the Mars Reconnaissance Orbiter", *JGR Planets* 114. [doi:10.1029/2009JE003342](https://doi.org/10.1029/2009JE003342)

---

## Synthetic demo terrain: `data/synthetic_demo/`

`scripts/make_synthetic_demo.py` generates a made-up 10 km × 10 km grid: 2,000 × 2,000 cells at 5 m,
with random seed 42, a base height of −4,500 m and two NoData patches. The tests use it, and the app
falls back to it only when the real dataset isn't there. Its metadata says `synthetic_demo`, and
the app shows a warning banner whenever it's active. It contains no real measurements.

## Coordinates

We use one convention everywhere: planetocentric latitude, east-positive longitude (−180° to 180°),
on the Mars sphere R = 3,396,190 m. The routing grid uses a local equidistant cylindrical projection
centred on **137.45°E, 4.6°S** (the middle of the study window):

```
x = R · cos(lat₀) · Δlon (radians)
y = R · Δlat (radians)
```

Across our window the scale error stays under 0.05%. Distances are reported in this plane, along
with the great-circle distance on the sphere.

## Checksums

`metadata.json` records SHA-256 checksums for the source DTMs and the processed grid, and
`download_data.py` checks the grid's checksum after downloading. The API shows them at `/api/datasets/{id}/provenance` and
`/integrity`. A matching checksum shows a file hasn't changed since we built it. It doesn't prove
where the original came from, and it doesn't prove the processing is scientifically right.

## Rebuilding the data yourself

`scripts/prepare_data.py` downloads the HiRISE DTMs and orthoimages, the USGS Gale DEM and the MOLA
DEM. It then merges, fills and clips them, and writes `data/hirise_gale/`. It needs several GB of
downloads and disk space, and the NASA servers can be slow. If a download fails, the script prints
the URL so you can fetch it in a browser and put it in `data/raw/`. Then run it again with
`--skip-download`. Add `--ortho-res 0.5` for the sharper photo layer.

## Libraries

The frontend uses React, TypeScript, Vite, CesiumJS (via Resium), Zustand and Recharts. The
display font is Space Grotesk (bundled, so it works offline). The backend uses FastAPI, NumPy,
rasterio, pyproj, Pillow and numba. An old OpenLayers 10.11.0 page (BSD-2-Clause) is kept in
`frontend/legacy/` and `frontend/static/ol/` for reference, and the current app doesn't use it.
