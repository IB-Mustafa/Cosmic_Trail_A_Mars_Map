"""Science cards and Mission Guide for COSMIC TRAIL.

Science cards
-------------
Curated facts about named sites in Gale Crater. Every claim has an explicit
source with enough information for the user to verify it. No claim is
presented as more certain than the cited evidence supports.

Mission Guide
-------------
A rule-based assistant that matches user questions to fact categories and
returns relevant science cards plus a text answer. It is NOT AI-generated,
it does NOT use a language model, and it always says so. It does not make
predictions or operational recommendations.
"""
from __future__ import annotations

import re
from typing import NamedTuple

GUIDE_DISCLAIMER = (
    "Mission Guide is a rule-based lookup system — it matches your keywords "
    "to a curated list of facts. It is NOT an AI and does NOT generate new text. "
    "All facts come from cited peer-reviewed papers or official NASA sources."
)

# ---------------------------------------------------------------------------
# Science cards
# ---------------------------------------------------------------------------
# Sources used (abbreviated references, full text in DATA_SOURCES.md):
#   [1] Grotzinger et al. 2014 — Habitable environment at Yellowknife Bay
#       Science 343(6169). doi:10.1126/science.1242777
#   [2] Vaniman et al. 2014 — Mineralogy at Yellowknife Bay
#       Science 343(6169). doi:10.1126/science.1243480
#   [3] Ming et al. 2014 — Volatiles at Yellowknife Bay
#       Science 343(6169). doi:10.1126/science.1245267
#   [4] Grotzinger et al. 2015 — Deposition, exhumation, and paleoclimate of an
#       ancient lake deposit, Gale crater, Mars. Science 350(6257). doi:10.1126/science.aac7575
#   [5] Wikipedia "Bradbury Landing" (citing NBC/NASA) — coordinates
#       Accessed 2024. As a secondary source; primary is NASA mission reports.
#   [6] NASA JPL — MSL Science Corner, public releases
#       https://science.nasa.gov/mission/msl-curiosity/
#   [7] Smith et al. 2001 — MOLA. JGR 106(E10). doi:10.1029/2000JE001364


class ScienceCard(NamedTuple):
    card_id: str
    site: str
    lon: float | None          # None when exact position not independently verified
    lat: float | None
    coord_confidence: str      # "published" | "approximate" | "unverified"
    summary: str
    detail: str
    tags: list[str]
    sources: list[dict]
    caveats: list[str]


CARDS: list[ScienceCard] = [
    ScienceCard(
        card_id="bradbury_landing",
        site="Bradbury Landing",
        lon=137.4417, lat=-4.5895,
        coord_confidence="published",
        summary="MSL Curiosity rover landing site (6 Aug 2012).",
        detail=(
            "Curiosity landed in Gale Crater on 6 August 2012. The landing site "
            "was named Bradbury Landing on 22 August 2012 in honour of science-fiction "
            "author Ray Bradbury. Nearby outcrops (Goulburn, Link, Hottah) show rounded "
            "pebbles consistent with an ancient streambed, suggesting liquid water once "
            "flowed through the area (NASA, 27 Sep 2012)."
        ),
        tags=["landing", "history", "water evidence", "streambed"],
        sources=[
            {"ref": "[5]", "text": "Wikipedia 'Bradbury Landing' citing NBC/NASA (coordinates 4.5895°S, 137.4417°E)."},
            {"ref": "[6]", "text": "NASA JPL MSL Science Corner."},
        ],
        caveats=[
            "Coordinates from secondary source (Wikipedia citing NBC). "
            "Primary mission coordinates may differ by tens of metres.",
            "Rounded pebbles are consistent with water transport but do not "
            "prove sustained habitability on their own.",
        ],
    ),

    ScienceCard(
        card_id="yellowknife_bay",
        site="Yellowknife Bay",
        lon=None, lat=None,
        coord_confidence="unverified",
        summary="Ancient habitable fluvial-lacustrine environment (confirmed).",
        detail=(
            "About 0.5 km NE of Bradbury Landing, Yellowknife Bay was reached in "
            "December 2012 (approximately sol 125). Two mudstone targets, John Klein "
            "and Cumberland, were drilled in the Sheepbed mudstone member. The mudstone "
            "contains smectite clay minerals, iron-bearing minerals, sulfates, and other "
            "compounds indicating a neutral-pH, low-salinity aqueous environment with "
            "moderate oxidation — conditions broadly consistent with the survival of "
            "some forms of life as we know it on Earth. The investigators concluded that "
            "this represents an ancient habitable environment. This does NOT mean life "
            "was present — habitability is a necessary but not sufficient condition."
        ),
        tags=["habitability", "mineralogy", "clay", "mudstone", "water evidence", "drilling"],
        sources=[
            {"ref": "[1]", "text": "Grotzinger et al. 2014. Science 343(6169). doi:10.1126/science.1242777"},
            {"ref": "[2]", "text": "Vaniman et al. 2014. Science 343(6169). doi:10.1126/science.1243480"},
            {"ref": "[3]", "text": "Ming et al. 2014. Science 343(6169). doi:10.1126/science.1245267"},
        ],
        caveats=[
            "Exact lon/lat coordinates are not independently verified here — the COSMIC TRAIL "
            "map marker is placed approximately ~0.5 km NE of Bradbury Landing.",
            "Habitability in geological record does NOT imply life was present.",
            "Smectite clays indicate past water but cannot determine its duration.",
        ],
    ),

    ScienceCard(
        card_id="aeolis_mons",
        site="Aeolis Mons (Mount Sharp)",
        lon=137.85, lat=-5.08,
        coord_confidence="published",
        summary="~5.5 km central mound with ancient lake and stream evidence.",
        detail=(
            "Aeolis Mons (informally 'Mount Sharp') rises approximately 5.5 km above "
            "the northern floor of Gale Crater. Its lower slopes preserve a stratigraphic "
            "record of alternating lake, stream, and aeolian deposits spanning an estimated "
            "3.3–3.8 Ga (billion years ago), suggesting long-duration habitable environments "
            "early in Mars history. Curiosity reached the base of Aeolis Mons in September 2014."
        ),
        tags=["stratigraphy", "lake", "habitability", "geology", "sediment"],
        sources=[
            {"ref": "[4]", "text": "Grotzinger et al. 2015. Science 350(6257). doi:10.1126/science.aac7575"},
        ],
        caveats=[
            "Central mound coordinates are approximate; the feature is several km across.",
            "Age estimates (3.3–3.8 Ga) are model-dependent and subject to revision.",
            "Lake/stream interpretation is based on sedimentary textures — alternative "
            "depositional mechanisms cannot be fully excluded.",
        ],
    ),

    ScienceCard(
        card_id="aeolis_palus",
        site="Aeolis Palus",
        lon=137.42, lat=-4.47,
        coord_confidence="approximate",
        summary="Broad crater floor between the landing site and Aeolis Mons.",
        detail=(
            "Aeolis Palus is the flat plain on the northern floor of Gale Crater, "
            "between the crater rim and the central mound Aeolis Mons. Curiosity "
            "traversed this terrain on its way from Bradbury Landing to Mount Sharp. "
            "The floor is covered in windblown sand and dust with scattered rock outcrops."
        ),
        tags=["terrain", "crater floor", "traversal"],
        sources=[
            {"ref": "[6]", "text": "NASA JPL MSL traverse maps."},
        ],
        caveats=[
            "Coordinates are approximate centre of the named region, not a point feature.",
        ],
    ),

    ScienceCard(
        card_id="mola_context",
        site="MOLA Context",
        lon=None, lat=None,
        coord_confidence="unverified",
        summary="Mars Orbiter Laser Altimeter — global topographic context.",
        detail=(
            "The Mars Orbiter Laser Altimeter (MOLA) on Mars Global Surveyor produced "
            "a global digital elevation model at ~463 m/pixel. The MOLA 463 m mosaic "
            "records elevations above the Mars areoid (the equipotential surface). "
            "Gale Crater floor is approximately 4.4–4.5 km below the areoid at the "
            "landing site. MOLA data are openly available (CC0) from USGS Astrogeology."
        ),
        tags=["mola", "topography", "data source", "global context"],
        sources=[
            {"ref": "[7]", "text": "Smith et al. 2001. JGR 106(E10). doi:10.1029/2000JE001364"},
        ],
        caveats=[
            "MOLA 463 m resolution cannot resolve features smaller than ~1 km. "
            "HiRISE DTM (1 m post spacing) is used for the route-analysis grid.",
        ],
    ),

    # --- NASA Space Apps official resources -------------------------------
    ScienceCard(
        card_id="curiosity_official_route",
        site="Curiosity's Proposed Path — Mount Sharp",
        lon=None, lat=None,
        coord_confidence="approximate",
        summary="NASA's official proposed traverse route for Curiosity ascending Mount Sharp.",
        detail=(
            "NASA scientists mapped a proposed route from Bradbury Landing through "
            "Yellowknife Bay, Pahrump Hills, Murray Buttes, and toward clay-bearing "
            "and sulfate-bearing units on Mount Sharp. COSMIC TRAIL's terrain-aware "
            "routing complements this plan by identifying the safest slope path "
            "between these science targets."
        ),
        tags=["NASA", "official route", "Curiosity", "Mount Sharp", "traverse plan"],
        sources=[
            {"ref": "NASA JPL Science",
             "text": "Curiosity's Proposed Path up Mount Sharp.",
             "url": "https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/"},
        ],
        caveats=[
            "The map overlay waypoints (GET /api/curiosity/route) are approximate positions, "
            "not the rover's measured traverse.",
            "COSMIC TRAIL routes are not certified safe for real EVA or rover operations.",
        ],
    ),

    ScienceCard(
        card_id="dust_storms",
        site="Gale Crater — Dust Storm Hazard",
        lon=None, lat=None,
        coord_confidence="unverified",
        summary="Mars global dust storms — major EVA hazard for visibility and solar power.",
        detail=(
            "Mars experiences regional and global dust storms that can last weeks "
            "to months. The 2018 global dust storm (MY34) caused Opportunity rover "
            "to lose power permanently. Curiosity (nuclear-powered) survived but "
            "REMS recorded 10x increase in atmospheric opacity.\n\n"
            "EVA IMPLICATIONS:\n"
            "• Visibility can drop to near zero in severe storms\n"
            "• Dust accumulation on suits increases thermal load\n"
            "• Atmospheric pressure spikes slightly during storms\n"
            "• Regional storms occur ~every Mars year; global storms less frequent\n\n"
            "NASA Worldview provides near-real-time dust tracking for Earth. "
            "For Mars, MARCI (Mars Color Imager) on MRO provides daily weather maps.\n\n"
            "RECOMMENDATION: Check MARCI daily weather reports before EVA planning. "
            "NASA Mars Weather: https://mars.nasa.gov/msl/weather/"
        ),
        tags=["dust storm", "weather", "hazard", "visibility", "EVA planning", "REMS"],
        sources=[
            {"ref": "NASA Worldview (Earth reference)", "text": "NASA Worldview.",
             "url": "https://worldview.earthdata.nasa.gov/"},
            {"ref": "MARCI Mars Weather", "text": "MSSS MARCI weather reports.",
             "url": "https://www.msss.com/msss_images/subject/weather_reports.html"},
            {"ref": "Guzewich et al. 2019 — 2018 Global Dust Storm",
             "text": "Guzewich et al. 2019, Geophysical Research Letters.",
             "doi": "10.1029/2018GL080839"},
        ],
        caveats=[
            "No real-time Mars weather data is used in COSMIC TRAIL. "
            "Dust storm risk is based on published statistics only.",
        ],
    ),

    ScienceCard(
        card_id="surface_imagery_context",
        site="Mars Surface — Visual Context for EVA Planning",
        lon=None, lat=None,
        coord_confidence="unverified",
        summary="NASA raw imagery from Mars rovers — visual ground truth for terrain assessment.",
        detail=(
            "NASA's Perseverance Raw Images Gallery provides over 1 million images "
            "from the Mars surface. While Perseverance operates in Jezero Crater "
            "(distinct from Curiosity's Gale Crater study area), the imagery provides:\n\n"
            "• Terrain texture reference: how rocky surfaces, sand, and dunes "
            "appear at ground level vs. orbital DEM data\n"
            "• Scale reference: 1-meter rocks appear in both HiRISE imagery "
            "and rover cameras\n"
            "• Dust devil and dust storm visual documentation\n"
            "• Rock abundance visual reference for EVA footing assessment\n\n"
            "For Gale Crater specifically, Curiosity's MAHLI and Mastcam images "
            "are archived at: https://mars.nasa.gov/msl/multimedia/raw-images/\n\n"
            "COSMIC TRAIL uses HiRISE DTM (1m resolution) for slope/terrain data, "
            "which corresponds to the scale visible in rover imagery."
        ),
        tags=["imagery", "Perseverance", "Curiosity", "surface", "visual context",
              "rock abundance", "terrain"],
        sources=[
            {"ref": "NASA Perseverance Raw Images", "text": "Mars 2020 raw images gallery.",
             "url": "https://mars.nasa.gov/mars2020/multimedia/raw-images/"},
            {"ref": "NASA Curiosity Raw Images", "text": "MSL raw images gallery.",
             "url": "https://mars.nasa.gov/msl/multimedia/raw-images/"},
        ],
        caveats=[
            "COSMIC TRAIL does not load live rover images. "
            "Images referenced for scientific context only.",
        ],
    ),
]

# ---------------------------------------------------------------------------
# Keyword → card mapping for the rule-based guide
# ---------------------------------------------------------------------------
RULES: list[tuple[list[str], list[str], str]] = [
    # (keywords, card_ids, response_text)
    (["landing", "landed", "curiosity", "rover", "2012", "msl"],
     ["bradbury_landing"],
     "Curiosity landed at Bradbury Landing on 6 August 2012."),
    (["water", "stream", "pebble", "rounded", "goulburn", "link", "hottah"],
     ["bradbury_landing"],
     "Rounded pebbles near the landing site are consistent with ancient water flow, "
     "but this is evidence for water, not proof of life."),
    (["yellowknife", "clay", "smectite", "mudstone", "habitable", "habitability",
      "john klein", "cumberland", "sheepbed"],
     ["yellowknife_bay"],
     "Yellowknife Bay contains smectite clays and other minerals indicating a past "
     "neutral-pH, low-salinity aqueous environment — an ancient habitable setting. "
     "No life has been detected."),
    (["life", "organism", "microbe", "biosignature", "alive"],
     ["yellowknife_bay", "aeolis_mons"],
     "No life has been detected on Mars. COSMIC TRAIL shows only geological evidence "
     "for past habitable conditions. Habitability is a necessary but not sufficient "
     "condition for life."),
    (["mount sharp", "aeolis mons", "sharp", "mound", "central peak"],
     ["aeolis_mons"],
     "Aeolis Mons rises ~5.5 km above the crater floor. Its lower strata record "
     "ancient lake, stream, and aeolian environments (~3.3–3.8 Ga)."),
    (["lake", "lacustrine", "sediment", "stratigraphy", "billion years"],
     ["aeolis_mons", "yellowknife_bay"],
     "Sedimentary evidence from Yellowknife Bay and Aeolis Mons strata indicates "
     "that Gale Crater hosted ancient lakes and streams."),
    (["mola", "laser altimeter", "topography", "elevation", "global"],
     ["mola_context"],
     "MOLA provides global topographic context at 463 m/px. Local routing uses "
     "the HiRISE 1 m DTM."),
    (["slope", "terrain", "safe", "route", "walk", "traversal", "traverse"],
     [],
     "Slope thresholds are based on Apollo EVA traverses and NASA MSL Engineering User Guide thresholds — see "
     "SCIENTIFIC_LIMITATIONS.md. No route in COSMIC TRAIL is certified safe "
     "for real EVA or rover operations."),
    (["mineral", "mineralogy", "iron", "sulfate", "oxide"],
     ["yellowknife_bay"],
     "Minerals identified at Yellowknife Bay include smectite clays, iron oxides, "
     "sulfates, and sulfides — consistent with a chemically diverse ancient aqueous "
     "environment (Vaniman et al. 2014; Ming et al. 2014)."),
    (["sol", "day", "mission day"],
     ["bradbury_landing"],
     "Curiosity's mission day 1 (sol 1) corresponds to 6 August 2012."),
    (["gale crater", "gale", "crater"],
     ["bradbury_landing", "aeolis_palus", "aeolis_mons"],
     "Gale Crater (~154 km wide) is the landing site of MSL Curiosity. "
     "Its floor, Aeolis Palus, sits ~4.5 km below the Mars areoid."),
    (["official route", "proposed path", "proposed route", "traverse plan",
      "pahrump", "murray buttes", "hematite"],
     ["curiosity_official_route"],
     "NASA's proposed Curiosity path runs from Bradbury Landing via Yellowknife Bay, "
     "Pahrump Hills and Murray Buttes toward clay- and sulfate-bearing units on Mount Sharp. "
     "It is shown on the map as the dashed gold reference line."),
    (["dust", "storm", "weather"],
     ["dust_storms"],
     "Mars dust storms can cut visibility and solar power for weeks; the 2018 global "
     "storm ended Opportunity's mission. COSMIC TRAIL uses no live Mars weather data — "
     "check MARCI weather reports before EVA planning."),
    (["image", "photo", "picture", "visual", "camera"],
     ["surface_imagery_context"],
     "NASA's rover raw-image galleries (Perseverance in Jezero, Curiosity in Gale) give "
     "ground-level visual context for terrain seen in orbital HiRISE data. "
     "COSMIC TRAIL links to them but does not load live images."),
]


def _keywords_match(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw in t for kw in keywords)


def _card_by_id(cid: str) -> ScienceCard | None:
    for c in CARDS:
        if c.card_id == cid:
            return c
    return None


def card_to_dict(card: ScienceCard) -> dict:
    return {
        "card_id": card.card_id,
        "site": card.site,
        "lon": card.lon,
        "lat": card.lat,
        "coord_confidence": card.coord_confidence,
        "summary": card.summary,
        "detail": card.detail,
        "tags": card.tags,
        "sources": card.sources,
        "caveats": card.caveats,
    }


def all_cards() -> list[dict]:
    return [card_to_dict(c) for c in CARDS]


def card_by_id(card_id: str) -> dict | None:
    c = _card_by_id(card_id)
    return card_to_dict(c) if c else None


def mission_guide_query(user_text: str) -> dict:
    """Rule-based query: returns matching cards and a text response.

    Does NOT use a language model. All answers come from the curated RULES table.
    """
    matched_card_ids: list[str] = []
    response_texts: list[str] = []
    for keywords, card_ids, text in RULES:
        if _keywords_match(user_text, keywords):
            matched_card_ids.extend(card_ids)
            response_texts.append(text)
    # de-duplicate while preserving order
    seen: set[str] = set()
    unique_ids = [cid for cid in matched_card_ids if not (cid in seen or seen.add(cid))]
    matched_cards = [card_to_dict(_card_by_id(cid)) for cid in unique_ids if _card_by_id(cid)]
    if not response_texts:
        response_text = (
            "No matching facts found for that query. "
            "Try asking about: Bradbury Landing, Yellowknife Bay, habitability, "
            "water evidence, Aeolis Mons, MOLA, slope, minerals, mission history, "
            "the official Curiosity route, dust storms, or rover images."
        )
    else:
        response_text = " ".join(response_texts)
    return {
        "disclaimer": GUIDE_DISCLAIMER,
        "query": user_text,
        "response": response_text,
        "matched_cards": matched_cards,
        "unmatched_note": (
            None if matched_cards else
            "No science cards matched this query. The Mission Guide only covers facts "
            "explicitly in its curated database."
        ),
    }
