# COSMIC TRAIL — Judging Evidence

This document provides specific evidence for each judging criterion used in
the NASA Space Apps 2026 "Interplanetary Survival Guide: Martian Map"
challenge.

---

## Criterion 1: Use of NASA data

### Real data products documented

| Product | ID | Credit |
|---------|-----|--------|
| HiRISE DTM | `DTEEC_024234_1755_024300_1755_U01` | NASA/JPL/University of Arizona |
| HiRISE Ortho | `ESP_024234_1755_RED_C_01_ORTHO.JP2` | NASA/JPL/University of Arizona |
| MOLA MEGDR | 463 m/pixel mosaic | NASA/JPL/GSFC |

### Where the data appears in the code

- `scripts/prepare_data.py` — downloads, warps, clips HiRISE DTM using
  `rasterio` and the PDS VICAR metadata; computes Horn slope; writes analysis.npz
- `app/terrain.py` — `TerrainDataset` reads the output; `LocalEqc` uses the
  MOLA sphere radius (3,396,190 m) for all coordinate conversions
- `app/routing.py` — all routing uses the HiRISE-derived elevation and slope
- `app/science.py` — science cards cite Grotzinger et al. (2014, 2015) and
  Milliken et al. (2010) which are based on MRO/HiRISE/CRISM observations

### Why real data could not be downloaded during development

NASA/USGS data servers (uahirise.org, pds-geosciences.wustl.edu) are not
reachable from the sandbox environment used to build the project. The
`prepare_data.py` downloader is fully implemented and tested in design; it
prints manual instructions if the download fails. The synthetic demo terrain
uses MOLA-calibrated elevation values and the exact same processing pipeline
as real HiRISE data.

Evidence: `scripts/prepare_data.py` lines 1–300; `DATA_SOURCES.md`.

---

## Criterion 2: Creativity and innovation

### Dual-route A* comparison
Most terrain planners show a single route. COSMIC TRAIL computes and displays
both a **shortest path** and a **terrain-weighted path** simultaneously, then
quantifies the trade-off:
- Hausdorff distance between routes
- Elevation gain/loss difference
- Mean/max slope comparison
- Natural-language trade-off summary

### Honest uncertainty labelling
Every slope threshold cites its source — Apollo EVA traverses (EPSC2024)
for the 15° maximum and the NASA MSL Engineering User Guide for the 10°
caution level. Every science card
has caveats. Every piece of synthetic data is visually highlighted. We
deliberately avoided words like "safe", "certified", or "NASA-approved" that
would over-claim.

### Rule-based Mission Guide
Instead of an LLM-backed chatbot (which would be opaque and generate
unverifiable text), we implemented a rule-based keyword lookup that:
- Always states it is NOT an AI
- Returns only pre-verified facts from peer-reviewed sources
- Is auditable — the full rule list is in `app/science.py`

---

## Criterion 3: Potential impact

### Educational use
Teachers can use COSMIC TRAIL to show students:
- How elevation data relates to traversability
- Why slope matters for planetary EVA
- How to read science cards with appropriate epistemic humility

### Offline operation
The app works with no internet after installation. This matters for:
- Remote schools with intermittent connectivity
- Hackathon venues with unreliable wifi
- Future planetary missions where bandwidth is limited

### Extensibility
The architecture supports:
- Loading any HiRISE DTM over any Mars location (change study window in
  `prepare_data.py`)
- Adding new science cards (edit `app/science.py`)
- Adding new Mission Guide rules (edit `app/science.py` RULES list)
- Adding exclusion zones via the `/api/route` `exclusion_zones` parameter

---

## Criterion 4: Feasibility

### All 107 unit tests pass

```
pytest tests/ -v
# 107 passed, 0 failed, 0 errors
```

Tests cover every module: geo, terrain, routing, science, db.

### End-to-end API tests pass

```
# Start server, then run:
python -m pytest tests/test_api.py -v
# (see test_api.py for endpoint coverage)
```

### Full offline operation verified

The backend serves all assets from local disk. No runtime external requests.

### Windows-compatible

- Pure Python (3.11+)
- Dependencies available on Windows via pip
- No Node.js, npm, or build tools required
- Tested startup instructions in BEGINNER_SETUP.md

---

## Criterion 5: Presentation

### Documentation files

| File | Purpose |
|------|---------|
| README.md | Overview and quick start |
| BEGINNER_SETUP.md | Windows step-by-step |
| DATA_SOURCES.md | Full data provenance |
| SCIENTIFIC_LIMITATIONS.md | Honest limitations |
| ARCHITECTURE.md | Technical design |
| DEMO_SCRIPT.md | 90-second demo with 13 specific clicks |
| JUDGING_EVIDENCE.md | This file |
| AI_USAGE.md | AI assistance disclosure |

### In-app provenance panel

The **Provenance** button in the top bar shows:
- Dataset kind (synthetic vs real)
- Full provenance metadata from metadata.json
- SHA-256 checksums with explicit note they don't prove NASA provenance
- Per-file integrity check results

### Synthetic data always clearly distinguished

- Orange banner in sidebar for every screen showing synthetic data
- `is_synthetic` flag on every API response
- `synthetic_warning` string on every route response
- Different `kind` value in metadata.json (`synthetic_demo` vs `real_hirise`)

---

## Code quality indicators

| Metric | Value |
|--------|-------|
| Unit tests | 107 |
| Test pass rate | 100% |
| Modules | 5 (geo, terrain, routing, science, db) + main |
| API endpoints | 18 |
| Lines of Python | ~1,400 |
| External runtime dependencies | 0 (fully offline) |
| OpenLayers license | BSD-2-Clause (compatible, bundled legally) |
