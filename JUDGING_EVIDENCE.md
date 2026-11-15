COSMIC TRAIL --- Judging Evidence (Updated Project Audit)
Purpose: This document separates data that is documented as
originating from NASA/USGS products, data that is generated or derived
by the project, approximate/demo content, and information fetched
remotely at runtime.

Audit basis: The project ZIP supplied for review, especially
data/hirise_gale/metadata.json, data/synthetic_demo/metadata.json,
DATA_SOURCES.md, data/README.md, the application source tree, and
the test results reported by the project developer. This is a
code-and-metadata audit, not an independent re-download or scientific
validation of every upstream product.
1. Data provenance: what is real, derived, approximate, or synthetic?
1.1 Main routing terrain: real-source data with a documented gap-fill
The active Gale Crater terrain dataset is identified in
data/hirise_gale/metadata.json as kind: real_hirise.

The metadata records five merged HiRISE DTM tiles:
- DTEEC_018854_1755_018920_1755_U01.IMG
- DTEEC_023957_1755_024023_1755_U01.IMG
- DTEEC_009505_1755_009571_009571_U01.IMG
- DTEEC_010573_1755_010639_010639_U01.IMG
- DTEEC_040770_1755_039280_1755_U01.IMG
The actual file names in the metadata are authoritative; check the
product IDs against their source pages before external publication. The
metadata also lists two candidate tiles skipped because they had no
valid data inside the study window.

Grid facts recorded in metadata:

  Measure                                        Recorded value
  Study window                   137.35--137.55°E, 4.75--4.45°S
Grid resolution                                           5 m
Grid dimensions                           2,364 × 3,558 cells
Total cells                                         8,411,112
Valid cells                                         8,399,272
Valid coverage                                         99.86%
Cells sourced from HiRISE                  7,417,993 (88.19%)
Cells filled from USGS DEM                   993,119 (11.81%)
Cells filled from MOLA                                 0 (0%)
95th-percentile slope                                  18.81°

Important distinction: the routing grid is not 100% HiRISE.
According to the dataset metadata, 88.19% of its cells are from the
merged HiRISE tiles and 11.81% are filled from the USGS MSL Gale Merged
DEM 1 m v3. The fill mask is recorded as usgs_filled in
analysis.npz. The USGS source is described as a HiRISE + CTX + HRSC
blend tied to MOLA, resampled from 1 m to 5 m and edge-blended to the
HiRISE surface.

This is a processed/derived dataset, not untouched raw instrument
output. The project processing notes describe merging, clipping,
resampling, reprojection, slope calculation, and gap filling.
1.2 HiRISE photo mosaic
data/hirise_gale/metadata.json records an available ortho_mosaic.tif
assembled from five HiRISE RED orthoimage products.

  Measure                                   Recorded value
  Pixel resolution                                     1 m
Study bounds              137.35--137.55°E, 4.75--4.45°S
Coverage fraction                                 88.17%
Missing source images                        None listed

The metadata says the source images were merged, histogram-matched, and
clipped; the first source wins in overlaps. This is a derived mosaic.
The coverage value means it does not cover every cell in the study
window.
1.3 Synthetic demonstration terrain
data/synthetic_demo/metadata.json identifies this dataset as
kind: synthetic_demo and explicitly states that it is mathematically
generated and does not represent actual Mars topography or NASA
measurements.

Its metadata records: - fixed random seed: 42; - grid: 2,000 × 2,000
cells at 5 m; - 99.62% valid coverage; - elevation base and procedural
terrain statistics for demonstration.

Use: demonstration/testing only. It must not be described as
measured Mars terrain or used as scientific/operational evidence.
1.4 Other bundled layers and their certainty
  Layer/resource          What the project uses                     Evidence status /
caveat
  Mineral detections      data/minerals/aqueous_minerals.json     Bundled detection-site
points attributed in
project documentation
to Ehlmann & Edwards
(2014), using
CRISM/OMEGA/THEMIS
context. These are
points/sites, not a
continuous mineral map.

  Geologic units          data/usgs_geologic_units.geojson        Project documentation
attributes the context
to Tanaka et
al. (2014), USGS SIM
3292. Polygons are
explicitly described as
simplified rectangles,
not boundaries
digitized from the
original map. One unit
assignment is marked
unverified in
DATA_SOURCES.md.

  Curiosity proposed path data/curiosity_official_route.geojson   Six named waypoints are
used as a reference
overlay. Project
documentation says only
Bradbury Landing has a
published coordinate;
the other waypoint
positions are
approximate and are not
rover traverse
telemetry.

  Hazard zones / dunes    data/hazard_zones.geojson               Approximate context
outlines. The Bagnold
Dunes boundary is
documented as
indicative, not a
surveyed boundary.

  Terrain context         data/terrain_context.npz                Bundled global/context
elevation resource
described by project
documentation as
MOLA-derived. Treat it
as a processed context
grid, not as the 5 m
local routing terrain.

  Place names             Frontend bundled gazetteer/labels         Local static reference
labels; not live
location updates.

  Weather facts           app/weather_facts.py                    Published historical
figures, not live Mars
weather and not a full
live REMS/RAD feed.
Science cards           app/science.py and related content      Curated explanatory
facts with literature
references; these are
authored content based
on cited publications,
not raw sensor data.
2. Remote resources versus local data
Remote at runtime
- The globe's colour basemap uses NASA Mars Trek WMTS tiles, with the
  URL template documented in DATA_SOURCES.md and implemented in
  frontend/src/components/Globe.tsx.
- Those tiles require an internet connection. The project
  documentation says the globe falls back to a plain base colour when
  tiles are unavailable.
Bundled/local at runtime
- Terrain analysis grids and masks.
- HiRISE photo mosaic.
- Mineral and hazard GeoJSON/JSON layers.
- Geologic-unit and Curiosity-route reference overlays.
- Place-name data and published weather/science facts.
The route planner, terrain queries, and assistant responses are computed
from the local application data/code. A result being calculated at
runtime does not mean the underlying measurement is live or newly
downloaded.
Assistant behaviour
Project documentation and source descriptions identify ARIA / Mission
Guide as rule-based, not an LLM-backed generative AI. It answers using
local data and authored rules/facts. Do not describe it as a live AI
model or a live Mars data feed.
3. What is verified, what is assumed, and what is calculated?
Use these labels in presentations and judging explanations:
  Label                   Meaning                 COSMIC TRAIL examples
  Source-documented   The project             HiRISE DTM product IDs;
metadata/docs identify  USGS MSL Gale DEM; HiRISE
an upstream source and  ortho products.
product. This audit has
not independently
authenticated the
upstream file.          

  Processed / derived Project code transforms 5 m routing grid, merged
source material into a  ortho mosaic, slope
usable layer.           raster, terrain-context
grid.

  Gap-filled          A value comes from      11.81% USGS-filled
another source where    routing-grid cells.
the primary source had
no data.                

  Approximate /         The project             Geology rectangles, most
inferred              documentation itself    Curiosity waypoint
warns that the geometry coordinates, dune
or assignment is        outline, flagged geology
approximate or          assignment.
unverified.             

  Synthetic           Generated               data/synthetic_demo/.
mathematically for
demonstration, not
measured on Mars.       

  Static published      A historical/published  ARIA weather figures and
fact                  value stored in code,   science-card facts.
not a current
observation.            

  Remote visual         Fetched from a remote   NASA Mars Trek basemap
resource              service when the        tiles.
application runs.       
Runtime calculation Computed by the app     Route paths, route
from bundled data and   metrics, terrain lookups,
algorithms.             rule-based assistant
responses.
Do not claim: 100% of the routing grid is HiRISE; all overlays are
precise; weather is live; Curiosity coordinates are a measured traverse;
the NASA basemap is offline; or checksums prove NASA provenance.
4. Data processing and application logic
The repository documents these relevant implementation locations:
  File / directory                      Role
  scripts/prepare_data.py             HiRISE terrain preparation
pipeline.

  app/terrain.py                      Loads terrain data and supports
terrain operations.

  app/routing.py                      Computes routes and route
comparisons from terrain inputs.

  app/context.py                      Supplies local contextual
information for route/assistant
responses.

  app/assistant.py                    Rule-based ARIA response logic.

  app/weather_facts.py                Stores published historical weather
facts.

  frontend/src/components/Globe.tsx   Globe display and remote basemap
configuration.

  data/hirise_gale/metadata.json      Main dataset provenance, coverage,
fill-source and checksum metadata.

  data/synthetic_demo/metadata.json   Synthetic dataset declaration and
generation metadata.

  DATA_SOURCES.md                     Project's source descriptions and
caveats.
SCIENTIFIC_LIMITATIONS.md           Scientific and operational
limitations.
The project documents a local-equidistant-cylindrical Mars coordinate
frame with radius 3,396,190 m and planetocentric latitude /
east-positive longitude conventions. The terrain metadata records a 5 m
analysis grid and a Horn 3×3 slope method.
5. Integrity checks and what they do not prove
The main terrain metadata contains SHA-256 checksums for source DTM
files and the processed analysis grid. The synthetic dataset also
contains checksums.

A matching checksum can show that a file has not changed relative to the
checksum record. It does not, by itself, authenticate the original
source, prove NASA ownership, validate the scientific processing, or
establish measurement accuracy. Source-page and product metadata should
be checked separately.
6. Test and build evidence
The developer reported the following results after the current project
edits:
  Check                               Result
  Frontend production build           Successful; Vite reported
(npm run build)                   built in 1.99s.

  Frontend bundle warning             Main JS bundle 812.73 kB minified,
above Vite's 500 kB advisory
threshold. This is a performance
warning, not a build failure.

  Backend test suite                  116 passed, 75 warnings, 138.22
(python -m pytest -q)             seconds.
Browser smoke check                 Developer confirmed the frontend
opened in the browser.
The 75 test warnings were reported as deprecation warnings from the
installed Starlette/FastAPI stack concerning
asyncio.iscoroutinefunction. They did not cause test failures.

These are developer-reported run results, not independently re-executed
as part of this document update.
7. Changes and remaining work
UI changes reported during this project session
- Removed the layer opacity slider from the layer control UI.
- Removed the Gap Fill layer toggle/control from the layer control UI.
- Removed the 3D exaggeration slider/control from the layer control
  UI.
These are UI removals. They do not, by themselves, prove that the
underlying gap-filling data, processing, or 3D terrain functionality has
been removed from the backend or data files.
Known documentation and review items
- Review DATA_SOURCES.md for stale statements that still describe
  the project as shipping only a synthetic demo; the supplied ZIP
  contains a real_hirise dataset as well.
- Reconcile old product IDs or descriptions in documentation with the
  current data/hirise_gale/metadata.json. The current metadata lists
  five merged DTM tiles and two skipped candidates; do not reuse a
  single older product ID as if it describes the entire merged
  dataset.
- Keep the geology, Curiosity waypoint, dune/hazard and
  historical-weather caveats visible in the UI/demo.
- Consider splitting the frontend JavaScript bundle; the current build
  warns that the main minified JS chunk exceeds 500 kB.
- Backend startup on the developer's Windows machine has not been
  confirmed in this audit. Passing API tests does not, by itself,
  prove the local server starts successfully under every Windows
  security policy.
8. Suggested judging explanation
COSMIC TRAIL combines source-documented Mars datasets with clearly
labelled derived, approximate, and synthetic resources. The local
routing grid is 5 m resolution and is documented as 88.19%
HiRISE-derived, with 11.81% of cells gap-filled from the USGS MSL Gale
merged DEM; valid coverage is 99.86%. The app also includes a derived
HiRISE ortho mosaic, reference mineral and geology layers, approximate
contextual overlays, and a separate synthetic demo dataset. Route
planning and terrain queries are calculated locally from bundled
inputs. The globe's colour basemap is fetched from NASA Mars Trek when
internet is available. Published weather values are historical, not
live. We distinguish source data from processing, estimates, and
generated demo content rather than presenting every layer as equally
authoritative.

9. Source files to inspect for supporting evidence
- data/hirise_gale/metadata.json
- data/synthetic_demo/metadata.json
- DATA_SOURCES.md
- data/README.md
- SCIENTIFIC_LIMITATIONS.md
- scripts/prepare_data.py
- scripts/make_synthetic_demo.py
- app/terrain.py
- app/routing.py
- app/context.py
- app/assistant.py
- app/weather_facts.py
- frontend/src/components/Globe.tsx
- tests