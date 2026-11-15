"""ARIA's place list — names a user can give as their position ("it's near Pahrump Hills").

Every coordinate comes from data the app already ships; nothing here is typed in by hand:

  Gale Crater sites (fuzzy-matched, typos allowed):
    science cards with published coordinates  → app/science.py (Bradbury Landing, Mount Sharp, Aeolis Palus)
    confirmed clay sites                      → app/context.py CONFIRMED_CLAY_SITES (Yellowknife Bay)
    Curiosity proposed-path waypoints         → data/curiosity_official_route.geojson (NASA JPL; APPROXIMATE)
  Mars-wide named features (exact name only)  → frontend/src/data/mars_labels.json
                                                 (IAU/USGS Gazetteer of Planetary Nomenclature centre points)

find_place()          → the best-matching place in a question, or None.
unknown_place_name()  → the place-like name a user gave that isn't in the list ("I'm at Olympus Mons" when
                         the gazetteer is missing), so ARIA can say exactly which name it doesn't know.
"""
from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

from . import aria_nlu as nlu
from . import context as ctx
from .science import CARDS

ROOT = Path(__file__).resolve().parent.parent
ROUTE_FILE = ROOT / "data" / "curiosity_official_route.geojson"
LABELS_FILE = ROOT / "frontend" / "src" / "data" / "mars_labels.json"

REGION_KM = 20.0           # IAU features at least this wide are regions, not a standing position
# Extra spoken forms of the Gale sites (the full name is always an alias too).
ALIASES = {
    "Bradbury Landing": ("bradbury",),
    "Yellowknife Bay": ("yellowknife",),
    "Pahrump Hills": ("pahrump",),
    "Murray Buttes": ("murray",),
    "Aeolis Mons (Mount Sharp)": ("mount sharp", "mt sharp", "aeolis mons"),
}
# Words that describe a kind of feature; a typo is only accepted in the distinctive part of a name.
GENERIC = {"hills", "hill", "bay", "landing", "ridge", "buttes", "butte", "unit", "mount", "mt", "mons", "palus",
           "crater", "bearing", "clay"}
# Things people say after "near"/"at" that are not place names.
NOT_PLACES = {"here", "there", "me", "it", "this", "that", "home", "the map", "the centre", "the center", "my location",
              "the moment", "the start", "the end", "the top", "the bottom", "mars", "the surface", "aria", "you",
              "this spot", "this place", "this point", "my position", "my spot", "the middle", "a", "an", "the"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower().replace("’", "'").replace("'", ""))).strip()


@lru_cache(maxsize=1)
def gale_places() -> tuple[dict, ...]:
    """Gale Crater sites with their coordinate source. First source of a name wins (most precise first)."""
    out: dict[str, dict] = {}

    def add(name, lon, lat, source, approximate, note=""):
        if name not in out and lon is not None and lat is not None:
            out[name] = {"name": name, "lon": float(lon), "lat": float(lat), "source": source,
                         "approximate": approximate, "note": note, "kind": "gale"}

    for c in CARDS:
        if c.lon is not None:
            add(c.site, c.lon, c.lat, f"COSMIC TRAIL science card “{c.site}” (published coordinates)",
                approximate=c.card_id != "bradbury_landing")
    for s in ctx.CONFIRMED_CLAY_SITES:
        add(s["name"], s["lon"], s["lat"], f"Curiosity results ({s['source']})", approximate=True)
    try:
        f = json.loads(ROUTE_FILE.read_text(encoding="utf-8"))["features"][0]["properties"]
        for w in f["waypoints"]:
            add(w["name"], w["lon"], w["lat"], "NASA JPL, Curiosity's Proposed Path up Mount Sharp (approximate waypoint)",
                approximate=True, note=w.get("note", ""))
    except (OSError, KeyError, IndexError, ValueError):
        pass
    for p in out.values():
        base = re.sub(r"\s*\(.*\)", "", p["name"])
        p["aliases"] = tuple(dict.fromkeys(_norm(a) for a in (base, *ALIASES.get(p["name"], ()))))
    return tuple(out.values())


@lru_cache(maxsize=1)
def iau_places() -> dict[str, dict]:
    """IAU feature names (lower-case alias → place) from the globe's bundled gazetteer."""
    try:
        d = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
        feats, src = d["features"], d.get("source", "IAU/USGS Gazetteer of Planetary Nomenclature")
    except (OSError, KeyError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for f in sorted(feats, key=lambda f: -(f.get("d") or 0)):        # the biggest feature wins a shared name
        name, kind = f["n"], f.get("t", "")
        place = {"name": name if kind != "Crater" else f"{name} Crater", "lon": float(f["lon"]), "lat": float(f["lat"]),
                 "source": f"{src} (feature centre)", "approximate": False, "kind": "iau",
                 "diameter_km": f.get("d"), "region": (f.get("d") or 0) >= REGION_KM}
        for alias in {_norm(name), _norm(place["name"])}:
            out.setdefault(alias, place)
    return out


def _gale_score(tokens: list[str], alias: str) -> float:
    """Best fuzzy score of `alias` against any same-length run of words in the question (0 if none)."""
    a = alias.split()
    best = 0.0
    for i in range(len(tokens) - len(a) + 1):
        window = tokens[i:i + len(a)]
        if window == a:
            return 1.0
        ratios = [difflib.SequenceMatcher(None, w, x).ratio() for w, x in zip(window, a)]
        distinctive = [r for r, x in zip(ratios, a) if x not in GENERIC]
        if (min(ratios) >= 0.75 and all(r >= 0.84 for r in distinctive) and distinctive
                and all(len(x) >= 5 for x in a if x not in GENERIC)):
            best = max(best, sum(ratios) / len(ratios))
    return best


def find_place(message: str) -> dict | None:
    """The place named in a question: Gale sites (exact, any case, or with a typo), then IAU names (exact)."""
    text = _norm(message)
    tokens = text.split()
    scored = [(_gale_score(tokens, a), len(a), p) for p in gale_places() for a in p["aliases"]]
    scored = [s for s in scored if s[0] > 0]
    if scored:
        score, _, p = max(scored, key=lambda s: (s[0], s[1]))
        return {**p, "match": "exact" if score == 1.0 else "fuzzy"}
    iau = iau_places()
    if not iau:
        return None
    # Multi-word names anywhere; one-word names only when written with a capital (not as the first word)
    # or followed by their feature type ("gale crater"), so ordinary words aren't taken for craters.
    msg = message.strip()
    caps = {_norm(m.group()) for m in re.finditer(r"\b[A-Z][\w'’-]+", msg) if m.start() > 0}
    for n in (4, 3, 2, 1):
        for i in range(len(tokens) - n + 1):
            alias = " ".join(tokens[i:i + n])
            p = iau.get(alias)
            if not p:
                continue
            if n == 1 and not (alias in caps and len(alias) >= 4 and alias not in nlu._VOCAB
                               and alias not in nlu._STOP):
                continue
            return {**p, "match": "exact"}
    return None


_LEAD = r"(?:it'?s|its|it is|i'?m|im|i am|we'?re|we are|i'?m standing|standing|currently|now|i'?m now)"
_PREP = r"(?:near|at|in|by|around|on|close to|next to|beside|from)"
PLACE_PATTERNS = [
    re.compile(rf"^\s*(?:ok(?:ay)?,?\s+|well,?\s+)?{_LEAD}\s+{_PREP}\s+(?:the\s+)?(.+?)\s*[?.!]*\s*$", re.I),
    re.compile(r"^\s*(?:and\s+|ok(?:ay)?,?\s+)?(?:what|how)\s+about\s+(?:at\s+|near\s+|in\s+|on\s+)?(?:the\s+)?(.+?)\s*[?.!]*\s*$", re.I),
    re.compile(r"^\s*(?:near|at|from)\s+(?:the\s+)?(.+?)\s*[?.!]*\s*$", re.I),
    re.compile(r"\b(?:near|at|in|around|from|close to|next to)\s+(?:the\s+)?"
               r"((?:[A-Z][\w'’-]+)(?:\s+(?:[A-Z][\w'’-]+|of|de|del|la))*)"),
]


def unknown_place_name(message: str) -> str | None:
    """A name the user gave as a location that is neither a known place nor an ordinary topic word."""
    for k, pat in enumerate(PLACE_PATTERNS):
        m = pat.search(message)
        if not m:
            continue
        cand = re.sub(r"^(?:a|an)\s+", "", m.group(1).strip(" ,;:\"'“”‘’"), flags=re.I)
        low = _norm(cand)
        words = low.split()
        if not words or len(words) > 4 or len(cand) > 40 or low in NOT_PLACES or cand in ("I", "ARIA"):
            continue
        p = nlu.understand(cand)
        if p.directions or p.time or p.why:
            continue
        # A topic word ("rock", "hills") can be part of a name: allow it only in a capitalised name
        # given as a location ("it's near Foo Rock"), not in "what about the rocks?".
        named = k in (0, 2) and any(w[:1].isupper() for w in cand.split())
        if p.topics and not named:
            continue
        if not any(len(w) >= 3 and w not in nlu._STOP for w in words):
            continue
        return cand
    return None


def known_place_names(limit: int = 6) -> list[str]:
    """Gale sites, nearest to the landing site first (those are inside the detailed 5 m map)."""
    ps = gale_places()
    if not ps:
        return []
    o = ps[0]
    near = sorted(ps, key=lambda p: ctx.distance_m(o["lon"], o["lat"], p["lon"], p["lat"]))
    return [re.sub(r"\s*\(.*\)", "", p["name"]) for p in near][:limit]
