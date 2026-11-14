# COSMIC TRAIL — AI Usage Disclosure

In the spirit of honest disclosure, this document describes how AI tools were
used in building COSMIC TRAIL.

---

## AI Tools Used

**Claude (Anthropic)** — conversational AI assistant, used throughout the
project to help write and debug Python code, documentation, and architecture.

---

## What AI Did

All first drafts were written by AI tools under direct team supervision and instruction. The scientific judgment, data selection, accuracy verification, and architectural decisions were made by the team.

| Task | AI role |
|------|---------|
| Initial architecture design | Suggested module structure; team reviewed and revised |
| `app/geo.py` | AI wrote first draft; team verified Mars sphere radius and projection formula against HiRISE PDS documentation |
| `app/terrain.py` | AI wrote first draft; team verified Horn (1981) formula and NoData propagation behaviour against published algorithm |
| `app/routing.py` | AI wrote first draft; team reviewed A* implementation, diagonal-block rule, and cost models |
| `app/science.py` | AI drafted science card text; **team verified every factual claim against cited peer-reviewed papers before accepting** |
| `app/db.py` | AI wrote SQLite CRUD boilerplate; team reviewed |
| `app/main.py` | AI wrote FastAPI endpoint structure; team reviewed |
| `frontend/index.html` | AI wrote the SPA; team reviewed OpenLayers integration |
| `scripts/make_synthetic_demo.py` | AI wrote; team verified slope statistics are walkable |
| `scripts/prepare_data.py` | AI wrote the rasterio processing pipeline; team reviewed HiRISE PDS format handling |
| Unit tests | AI wrote `tests/test_core.py`; team reviewed test assertions |
| Documentation | AI drafted all .md files; team reviewed for honesty and accuracy |

---

## What AI Did NOT Do

- AI did not independently verify NASA data URLs against live PDS servers
  (network access was restricted in the development environment).
- AI did not write Mission Guide rules — those were written by the team
  based on reading the cited papers.
- AI did not select which science facts to include — the team read the papers
  and chose what to include and how to caveat it.
- AI did not decide the slope thresholds — the team chose 15° (max) and
  10° (caution) from Apollo EVA traverses (EPSC2024) and the NASA MSL
  Engineering User Guide, and cites those sources wherever they are shown.

---

## Human Oversight Applied

- Every science card fact was verified against the cited paper before being
  accepted into the codebase.
- All caveats (mineralogy ≠ life, slope-threshold sourcing, etc.) were written
  by the team, not by AI.
- The honest-disclosure approach (no "safest route" claims, no "NASA-approved"
  labels) was a deliberate team decision.
- All 107 unit tests were reviewed by the team before submission.

---

## Mission Guide vs AI

The Mission Guide in COSMIC TRAIL is explicitly **NOT** an AI:
- It is a hand-written rule list in `app/science.py`
- It performs keyword matching, not text generation
- Every response string was written by the team
- It always displays: "Mission Guide is a rule-based lookup — it is NOT an AI"

This distinction was intentional: a generative AI for science facts could
produce plausible-sounding but unverifiable claims. We chose a rule-based
approach so every statement in the app can be traced to a source.

---

*Team CosmicGirls · NASA Space Apps 2026*
