COSMIC TRAIL — Data Verification, Sources & Runtime Evidence
Purpose: This document explains which data/resources the project uses, where the project says they come from, what was checked in the supplied project files, and which parts are static, remote, derived, approximate, or calculated at runtime.

1. Verification scope — what “verified” means here
This review inspected the supplied project archive and its source files, including dataset metadata, data-source documentation, application code, and frontend implementation.

Verified within the project: file presence, metadata fields, declared source/product names, dataset dimensions and coverage figures recorded in metadata, code paths that load data, and whether a feature is local, remote, static, or calculated.

Not independently authenticated: original upstream NASA/USGS downloads were not re-downloaded and compared against official archives as part of this review. Therefore, source attribution below means documented by the project, not independently certified by this audit. SHA-256 checksums verify file consistency against the checksum record; they do not independently prove source ownership or scientific accuracy.
2. Data inventory and source evidence
2.1 Main Gale Crater terrain — HiRISE DTM with USGS gap-fill
Project files: data/hirise_gale/metadata.json, data/hirise_gale/analysis.npz, and scripts/prepare_data.py.

The metadata identifies the active dataset as kind: real_hirise and records five merged HiRISE DTM tile products:
- DTEEC_018854_1755_018920_1755_U01.IMG
- DTEEC_023957_1755_024023_1755_U01.IMG
- DTEEC_009505_1755_009571_009571_U01.IMG
- DTEEC_010573_1755_010639_010639_U01.IMG
- DTEEC_040770_1755_039280_1755_U01.IMG
The metadata also records two candidate tiles skipped because they had no valid data inside the study window.
Metadata measurement	Recorded value
Study bounds	137.35–137.55°E, 4.75–4.45°S
Analysis grid resolution	5 m
Grid dimensions	2,364 × 3,558 cells
Total cells	8,411,112
Valid cells	8,399,272
Valid coverage	99.86%
HiRISE-sourced cells	7,417,993 (88.19%)
USGS DEM-filled cells	993,119 (11.81%)
MOLA-filled cells	0 (0%)
95th-percentile slope	18.81°


Important: the routing grid is not 100% HiRISE. Metadata says 88.19% of cells come from merged HiRISE tiles and 11.81% are filled using the USGS MSL Gale merged DEM 1 m v3. The USGS source is described in project metadata as a HiRISE + CTX + HRSC blend tied to MOLA, resampled from 1 m to 5 m and edge-blended with the HiRISE surface. The fill mask is stored in analysis.npz as usgs_filled.

This is a processed product, not untouched instrument output. The project pipeline performs merging, clipping, reprojection/resampling, slope calculation, and gap filling.
2.2 HiRISE orthophoto mosaic
Project file: data/hirise_gale/metadata.json.

The metadata records an ortho_mosaic.tif assembled from five HiRISE RED orthoimage products.
Metadata measurement	Recorded value
Pixel resolution	1 m
Coverage fraction	88.17%
Source images missing	None listed


The mosaic is derived: metadata describes merging, histogram matching, and clipping, with the first source taking precedence in overlaps. It does not cover the entire study window.
2.3 Global Mars elevation/context
Project resource: data/terrain_context.npz and the globe's terrain-loading code.

The project describes the broader terrain context as MOLA-derived. Treat this as a bundled, processed context grid; it is distinct from the higher-resolution 5 m local Gale routing grid. The frontend terrain code documents HiRISE/USGS heights in the routing region and MOLA context elsewhere.
2.4 Global Mars imagery basemaps — remote NASA Mars Trek tiles
Implementation: frontend/src/components/Globe.tsx.

The globe defines remote tile services from NASA Mars Trek:
- Viking MDIM 2.1 colour mosaic — documented in code as approximately 232 m/pixel.
- MGS MOLA colour-shaded relief — documented in code as approximately 463 m/pixel for the whole-Mars view.
These are fetched as WMTS/tile imagery while the application runs and require an internet connection. They are not bundled offline imagery. Code comments say the globe falls back to a plain base colour if remote imagery is unavailable; local application layers can still be used.
2.5 Mineral detection locations
Project file: data/minerals/aqueous_minerals.json.

Project documentation attributes these mineral detection/site points to Ehlmann & Edwards (2014), using CRISM/OMEGA/THEMIS instrument context. These are site/detection points, not a continuous mineral abundance map and not a live instrument feed. Their display is based on bundled JSON data.
2.6 Geologic units
Project file: data/usgs_geologic_units.geojson.

Project documentation attributes the geological context to Tanaka et al. (2014), USGS Scientific Investigations Map 3292.

Caveat: the supplied project represents the units using simplified rectangle geometries. Do not present these as precise, fully digitized geological boundaries.
2.7 Curiosity route and landing-site references
The project includes a proposed/reference route with six waypoints. The audit found only Bradbury Landing's coordinate documented as firm; the other waypoint positions are approximate. This is not a rover telemetry track and should not be described as the exact path driven by Curiosity.

Landing-site labels and the place-name gazetteer are bundled reference content, not live location updates.
2.8 Hazard and dune overlays
The project includes hazard/dune outline data as bundled local overlays. Their geometry is documented as approximate/indicative, not a surveyed or operationally certified hazard boundary. Treat them as visualization/context, not safety-critical navigation data.
2.9 Weather and science facts
Weather implementation: app/weather_facts.py.
Science content: app/science.py and related bundled content.

Weather values are published/historical facts stored in application code. They are not live Mars weather observations and are not a continuously updated REMS/RAD feed. Science cards are curated explanatory content with literature references, not raw live sensor measurements.
2.10 Synthetic demo terrain
Project file: data/synthetic_demo/metadata.json.

The metadata explicitly labels this dataset kind: synthetic_demo and says it is mathematically generated rather than measured Mars topography. Recorded characteristics include fixed random seed 42, a 2,000 × 2,000 grid at 5 m spacing, and 99.62% valid coverage.

Use this dataset for demonstration/testing only. It must not be described as real Mars measurements or NASA instrument data.
3. Static, remote, and dynamic/runtime parts
“Dynamic” can mean either fetched from a remote service or calculated by the application. These are different behaviours, so they are separated below.
Project element	Where it comes from	Behaviour in the app
HiRISE/USGS Gale routing terrain	Bundled local files under data/hirise_gale/	Static input data loaded locally; terrain values/lookups are used at runtime
HiRISE orthophoto mosaic	Bundled ortho_mosaic.tif	Static local imagery
MOLA terrain context	Bundled data/terrain_context.npz	Static local context data
Mineral detections	Bundled JSON	Static local points
Geologic units	Bundled GeoJSON	Static local overlay
Curiosity waypoints/route reference	Bundled project data	Static reference geometry; route proposals/calculations are generated by the app
Hazard/dune outlines	Bundled project data	Static approximate overlays
Gazetteer/place labels	Bundled frontend data	Static local labels
Weather facts	app/weather_facts.py	Static published/historical facts; not live weather
Science cards	app/science.py and related content	Static curated facts
Viking MDIM 2.1 basemap	NASA Mars Trek tile service	Remote/dynamic fetch; requires internet
MOLA shaded-relief basemap	NASA Mars Trek tile service	Remote/dynamic fetch; requires internet
Terrain tiles/API responses	Backend reads local terrain data and serves responses	Runtime delivery/computation, not necessarily a live external feed
Route path, distance/cost and comparisons	app/routing.py using local terrain/context	Calculated at runtime
Terrain queries/profile/slope results	app/terrain.py and local terrain inputs	Calculated at runtime
ARIA / Mission Guide answers	app/assistant.py, app/context.py, local facts/rules	Rule-based runtime responses; not an LLM-backed live Mars AI service


Key distinction: a route or terrain result can be calculated dynamically even though the underlying terrain measurements are static bundled data. A basemap can be remotely fetched while scientific overlays and routing inputs remain local.
4. Application processing and code locations
File or directory	Role evidenced by the project
scripts/prepare_data.py	Prepares/merges terrain data and creates analysis products
app/terrain.py	Loads terrain data and supports terrain operations
app/routing.py	Calculates route paths and comparisons
app/context.py	Supplies local contextual information
app/assistant.py	Implements rule-based ARIA response logic
app/weather_facts.py	Stores published/historical weather facts
frontend/src/components/Globe.tsx	Globe display, terrain provider and remote basemap configuration
frontend/src/api/cosmic.ts	Frontend API helpers for terrain and feature resources
data/hirise_gale/metadata.json	Main terrain provenance/coverage/fill/checksum metadata
data/synthetic_demo/metadata.json	Synthetic dataset declaration and generation metadata
DATA_SOURCES.md	Project source descriptions
SCIENTIFIC_LIMITATIONS.md	Scientific/operational limitations


The project documents a local equidistant cylindrical Mars coordinate frame, Mars radius 3,396,190 m, planetocentric latitude, and east-positive longitude. Terrain metadata records a 5 m analysis grid and a Horn 3×3 slope method.
5. What can and cannot be claimed
Supported by the supplied project files
- The project contains a dataset explicitly labelled real_hirise with five merged HiRISE DTM tile IDs.
- Its metadata records 5 m grid resolution and the coverage/source percentages listed above.
- The routing grid includes a documented 11.81% USGS gap-fill component.
- The project contains a derived HiRISE orthophoto mosaic.
- The project contains separate MOLA-derived context data and remote NASA Mars Trek basemap definitions.
- The project includes bundled mineral, geology, route, hazard/dune, gazetteer, weather, and science reference content.
- The project separately labels its synthetic demo terrain as mathematically generated.
- Route planning and ARIA responses are implemented in local application code.
Claims to avoid
- “Every terrain cell is HiRISE” — incorrect; metadata records 11.81% USGS-filled cells.
- “All map layers are live NASA data” — incorrect; many layers are bundled static files.
- “Mars weather is live” — unsupported; weather facts are historical/published values stored in code.
- “ARIA is a generative AI model connected to NASA” — unsupported; project implementation is rule-based.
- “The Curiosity line is the exact rover traverse” — unsupported; most waypoint positions are approximate.
- “Geology/hazard outlines are exact surveyed boundaries” — unsupported; project geometry is simplified/approximate.
- “The synthetic demo is real Mars terrain” — incorrect.
- “A checksum proves NASA provenance or scientific accuracy” — incorrect.
6. Integrity and reproducibility
The main terrain metadata records SHA-256 checksums for source DTM files and the processed analysis grid; the synthetic dataset also records checksums.

A matching checksum shows that a file matches the checksum value recorded in metadata. It does not independently authenticate the original download, prove NASA/USGS ownership, validate the processing method, or establish scientific accuracy. For formal scientific claims, upstream product pages and original archive files should be checked independently.
7. Build and test evidence
The following results were reported by the project developer during this project review:
Check	Reported result
npm run build	Successful; Vite reported built in 1.99s
Frontend bundle	Main minified JS bundle reported as 812.73 kB; Vite issued an advisory warning because it exceeds 500 kB
python -m pytest -q	116 passed, 75 warnings, in 138.22 seconds
Browser check	Developer confirmed that the frontend opened in a browser


The 75 warnings were reported as Starlette/FastAPI deprecation warnings involving asyncio.iscoroutinefunction. These results are developer-reported and were not independently rerun while preparing this document.

Backend startup limitation: a successful local backend server startup on the developer's Windows machine was not confirmed in this review. Passing automated tests does not by itself establish that the server starts under every Windows security policy.
8. Suggested explanation for judges
“Cosmic Trail combines a high-resolution Gale Crater terrain dataset documented as being built from HiRISE DTMs, with USGS DEM gap filling where the HiRISE source has missing coverage. The project metadata records a 5 m analysis grid with 99.86% valid coverage: 88.19% HiRISE-sourced and 11.81% USGS-filled. We also use a derived HiRISE orthophoto mosaic, MOLA-derived broader terrain context, and NASA Mars Trek imagery tiles for the global visual basemap. Mineral, geology, Curiosity waypoint, hazard, place-name, weather and science information is included as local reference content, with documented approximations and historical/static limitations. The app calculates route results and terrain queries at runtime from local data; its ARIA guide uses rule-based responses. A separate synthetic dataset is provided for demo/testing and is not presented as measured Mars terrain.”
9. Review note
This document is a transparent code-and-metadata audit of the supplied project archive. It distinguishes project-declared sources from independently authenticated source files, and static inputs from remote resources and runtime calculations. If the dataset is used for formal scientific publication or operational decisions, verify the original upstream NASA/USGS products and processing independently.