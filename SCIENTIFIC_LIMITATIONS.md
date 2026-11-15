# What COSMIC TRAIL can and can't tell you

We built COSMIC TRAIL to plan routes from real data, and we'd rather be clear about where that data
and our methods fall short than oversell them. This page is for judges, teachers and anyone who
wants to know how far to trust a route.

**The short version:** our routes avoid ground that is steep on a 5 m grid. They don't know about
rocks, loose sand, dust storms or anything smaller than about 5 m, so they're a planning aid, not a
safety guarantee.

---

## Terrain

### HiRISE DTMs

- HiRISE DTMs can have jitter artefacts, shadowed patches, and holes where stereo matching failed.
  We fill holes from the USGS Gale DEM (below). Any cell still without a height can't be walked.
- HiRISE DTMs have about 1 m post spacing, but we route on a 5 m grid. Rocks and drops smaller than
  about 5 m are invisible to the router. Real EVA or rover safety needs much finer hazard mapping.

### Gap fill from the USGS Gale DEM

Our five HiRISE DTMs leave 11.81% of the 5 m grid without heights. That's 993,119 cells, mostly
between the image strips. We fill only those cells, from the USGS MSL Gale Merged DEM 1 m v3
(HiRISE + CTX + HRSC). HiRISE values are never replaced.

- **The resolution isn't the same everywhere.** 1 m is the USGS mosaic's grid spacing. Where USGS
  built it from CTX or HRSC rather than HiRISE, the real detail is coarser.
- **The filled areas are steeper.** In the current build, the median slope is 11.5° in filled cells
  and 3.4° in HiRISE cells, and the 95th percentile is 30° against 14°. The gaps fall mostly on
  rougher ground, so routes crossing filled areas meet more blocked and caution cells. That reflects
  the terrain, not an error, but it's worth knowing.
- **We shift the heights to match.** Where both exist, our HiRISE surface sits higher than the USGS
  mosaic: by 8.66 m at the median, and 0.85–18.07 m between the 5th and 95th percentiles. So there's
  no step at the gap edges: we spread that offset smoothly across each gap (Laplace interpolation)
  and add it to the USGS heights. The filled heights are therefore adjusted to our HiRISE tiles,
  not the values USGS published (a correction of 4.98–22.79 m, 5th–95th percentile). Ground just
  inside the gap edges stays a bit rougher: its 95th-percentile slope is about 25°, against 14° in
  HiRISE areas.
- **There's a small horizontal offset between the products.** Where both exist, the USGS mosaic
  places features about 30–45 m east (and up to 30 m north or south) of the HiRISE DTMs. We
  measured this on 12 November 2026 by cross-correlating 805 m patches. Each part of the grid
  follows its own source, so a small step can show at gap boundaries.
- **The fallback is much coarser.** Without the USGS file, `prepare_data.py` falls back to the MOLA
  463 m DEM. That's about 90× coarser, so slopes in those areas would come out too gentle.
  `metadata.json` (`fill_source`) records which source was used. The current build uses USGS
  everywhere and MOLA nowhere.
- **You can always tell which cells are filled.** The masks are stored in `analysis.npz`
  (`usgs_filled`, `mola_filled`) and counted in `metadata.json`, and the hover bar shows the source
  of the point under your cursor.

### HiRISE DTMs in the wider Gale area

We searched the HiRISE cumulative DTM index
(`https://www.uahirise.org/PDS/INDEX/DTMCUMINDEX.TAB`, 12 November 2026) for 137.1–137.8°E,
5.2–4.0°S, and found **18 elevation DTMs**. Seven of them we use or tried: the five we merge, plus
`024234` and `001488`, which have no data inside our window. Every candidate is listed with its size
and PDS path in `ADDITIONAL_DTM_FILES` (`scripts/prepare_data.py`). We don't download them
automatically, because they're 128–833 MB each.

- **Could still improve our window:** `009149` and `009650`, plus slivers of `019698` and `011417`.
- **Outside our window** (only useful if we widen it): `062963` (Peace Vallis, 2 m posts),
  `018788`, `012551`, `006855`, `012340`, `008147`.
- **Areas with no HiRISE DTM at all:** the western edge (137.1–137.2°E, north of about 4.7°S),
  north-east Aeolis Palus (north of about 4.3°S, 137.4–137.8°E) and central Aeolis Mons (east of
  about 137.5°E, south of about 4.75°S). HiRISE DTMs only exist where a stereo pair was targeted and
  processed, and in Gale those cluster around the old landing ellipse and Curiosity's route.
  Elsewhere the USGS mosaic or MOLA are the only height sources.
- **Widening the window has a cost.** The full 0.7° × 1.2° area at 5 m would be about 8,300 ×
  14,200 cells (around 118 million), compared with 8.4 million today. Routing time and memory
  would need another look before we widen `STUDY_WINDOW`.

### Projection

- The local equidistant cylindrical projection is centred on 137.45°E, 4.6°S, and its scale error
  grows away from the centre. Across our window (about 11.8 km × 17.8 km) it stays under 0.05%.
- We treat Mars as a sphere (R = 3,396,190 m), and heights are relative to the MOLA areoid. That's
  fine for relief, but heights above the sphere aren't true radii.

---

## The 3D globe

- **Heights are true (1×).** We removed the old vertical exaggeration slider, so what you see is the
  real relief. Routing, slopes, the elevation chart and every number use the same true heights.
- **Resolution varies across the globe.** Inside the routing area the globe uses our 5 m grid.
  Outside it uses MOLA: 463 m around Gale (131–144°E, 11°S–2°N) and averaged to 1/8° (about
  7.4 km) elsewhere. Mount Sharp, the crater rim and distant terrain look much smoother than the
  routing area, and the averaged grid understates extremes (the Hellas floor shows as about
  −7.4 km instead of about −8.2 km).
- **The grid edge is blended.** Within 300 m of the grid's edge we blend the grid and MOLA linearly
  to avoid a wall. Near Bradbury Landing they differ by a few metres, but elsewhere (up to about 20 m
  where we checked) the band is a smooth ramp, not real terrain.
- **Labels can flicker while tiles load.** Labels behind terrain are hidden with one ray test each
  against the tiles loaded so far, so a name can briefly appear or vanish while tiles stream in.
- **The basemap is coarse.** The Viking colour basemap (232 m/px) is far coarser than HiRISE and
  needs internet. Offline, the globe shows a plain colour.
- **Without MOLA the globe is flat.** `data/terrain_context.npz` is built separately with
  `scripts/build_terrain_context.py`, which needs the 2 GB MOLA DEM. Without it, the globe is flat.

## The HiRISE photo

- **Native resolution is the limit.** The default mosaic is 1 m/px (HiRISE `RED_C` orthoimages), and
  the optional build is 0.5 m/px (from the 0.25 m `RED_A` images). The camera stops where one photo
  pixel would cover more than about 1.5 screen pixels. Zooming further would only blur it, not add
  detail.
- **It covers 88.17% of the window.** The rest shows the basemap underneath.
- **Strips don't match perfectly.** The five images were taken years apart under different sun
  angles. We histogram-match them, but seams between strips can still differ in brightness.
- **The contrast is stretched.** We apply one fixed stretch (half histogram equalisation) to every
  tile so the photo is readable. There's no sharpening and no upscaling.

## Minerals

- **What it is.** These are 2,417 detection sites from Ehlmann & Edwards (2014), via NASA Mars Trek:
  1,648 phyllosilicates, 344 chlorides, 207 sulfates, 182 silica and 36 carbonates.
- **It's not a mineral map.** Each point marks a published detection (about ±0.01°), not the extent
  of a deposit. No point doesn't mean no mineral.
- **Gale coverage is sparse.** Seven sites lie within about 150 km of Bradbury Landing, and none are
  inside the routing area. The nearest is a phyllosilicate detection on Mount Sharp's flank
  (137.64°E, 5.33°S). The layer gives regional context, not route-scale geology.
- **There's no CRISM image layer.** The Mars Trek layer `MRO_CRISM_MSW_226PPD_v02` doesn't exist
  (HTTP 404 when we checked on 13 November 2026), and Mars Trek has no CRISM mineral raster over
  Gale. That would need pixel-level CRISM products from the PDS.
- **The colours are the product's own:** phyllosilicates blue, sulfates pink (#ff6699, though Trek's
  description says "orange"), silica purple, chlorides yellow, carbonates green.

---

## Routing

### Slope limits

Routes never cross a slope over **15°**, and stretches of **10–15°** are flagged. We took the 15°
limit from Apollo astronauts' experience on slopes (EPSC2024-196). It also matches the "high slope"
boundary in JPL's MSL engineering guide, where the 10° caution comes from: in loose sand, tilts
under 10° give 0–25% upslope slip. These are planning guides from past missions. They haven't been
validated for this terrain model or for future Mars suits.

### Slope method

We use Horn's (1981) 3×3 formula. Border cells and cells next to a hole can't be computed, so
they're treated as impassable. That can occasionally block a walkable edge cell.

### No corner-cutting

A diagonal step is only allowed when both side cells are walkable. That stops routes squeezing
between two blocked cells, and sometimes makes them a little longer than a person would walk.

### Long routes

Routes longer than 3 km may come from the corridor search: a coarse 20 m route first, then a
full-resolution search inside a corridor around it. That route is the best one inside the corridor.
Our tests check it's within 2% of the true optimum on a full-length route across the study area.
Each route reports whether it came from the `exact` or the `corridor` search.

### What routes ignore

Routes don't account for dust storms, loose regolith, rocks smaller than about 5 m, buried voids,
radiation, lighting or time of day. Those all matter for a real EVA, and none of them are in our
data.

### Distances and times

Lengths are measured in the local map plane, plus a great-circle distance and a 3D length that
follows the elevation changes (an estimate, not a true surface integral). Travel time is the 3D
length divided by 4 cm/s, Curiosity's top speed on flat, hard ground. Real drives are slower, so
treat it as a lower bound.

---

## Science cards

- **Coordinates carry a confidence label.** "published" comes from a paper or a NASA report,
  "approximate" was estimated from maps (± a few hundred metres), and "unverified" comes from
  general descriptions. Don't use approximate or unverified positions for navigation. The
  Bradbury Landing card says its coordinates come from a secondary source.
- **Minerals aren't proof of water or life.** The cards describe mineral evidence that scientists
  read as signs of past water. That doesn't prove liquid water, and it doesn't prove past or present
  life, and every card says so.
- **The facts may date.** They come from papers up to 2024. Mars research moves on, and newer work
  may refine them.

## ARIA

- **No language model.** ARIA reads your question with hand-written rules: typo fixing, topic
  words, compass directions, place names, and follow-ups based on the last few messages. Then it
  builds the answer from our data. It handles a lot of wordings, but it doesn't really understand
  free text. If a question is too far from what it knows, it says so and suggests questions it can
  answer.
- **"Here" means the centre of the map,** unless you name a place it knows. Outside the 5 m grid it
  can only give a rough MOLA height.
- **It never gives a safety verdict.** Slope answers use the 5 m grid and the router's 10° and 15°
  limits. Direction checks ("is it safe to go north?") look at a 500 m sector of the grid in that
  direction, which isn't a planned route. Boulders, sand and dust aren't in the data.
- **The weather isn't live.** No REMS or RAD data is loaded. ARIA quotes published figures (about
  0 °C and −70 °C from PIA16913, and about 0.64 mSv per day from Hassler et al. 2014) and says
  they're historical. For wind, pressure and dust it says it has no local readings, and gives only
  general Mars facts.
- **It's an offline helper, not mission advice.** Every answer ends with its sources, so you can
  check them.

The older keyword **Mission Guide** (`POST /api/guide/query`) is still in the backend, but the app
no longer uses it. ARIA replaced it.

---

## Things COSMIC TRAIL doesn't claim

| Claim | What's true |
|-------|-------------|
| "The safest route" | No route here is certified safe. The terrain-safe route avoids steep ground on a 5 m grid. |
| "NASA-approved" | This is a student hackathon project, not a NASA product. |
| "Every terrain cell is HiRISE" | 88.19% is HiRISE, and 11.81% is filled from the USGS Gale DEM. |
| "Live Mars weather" | The weather figures are published historical values. |
| "The Curiosity line is the rover's real track" | It's NASA's proposed path, with approximate waypoints. |
| "ARIA is an AI connected to NASA" | ARIA is rule-based and offline. |
| "Subsurface or dust hazards" | We have no data on either. |

## The synthetic demo terrain

`data/synthetic_demo/` is generated from a fixed random seed and doesn't represent real Mars terrain.
The tests use it, and the app only falls back to it when the real data is missing. When that happens,
the app shows a warning banner, and any routes on it have no scientific meaning.

---

*Team cosmiCore, NASA Space Apps Challenge 2026. COSMIC TRAIL is a learning prototype, not a
mission-planning system.*
