"""ARIA — Astronaut Route Intelligence Assistant (rule-based, fully offline, no language model).

Understanding (app/aria_nlu.py): normalises the question (typos, short forms, repeated letters),
finds every topic and modifier in it (day/night, comparison, directions, "why"), and resolves
follow-ups ("and at night?", "what about south?") against the previous answer.

Answers are COMPUTED here from data the backend already loaded, then worded by
app/aria_templates.py as: direct answer → reason with the real numbers → practical tip →
optional offer → "Source: …":

  slope / safety / directions → the 5 m analysis grid (HiRISE DTMs + USGS gap fill)
  outside the grid            → MOLA 463 m context heights (data/terrain_context.npz)
  route questions             → the route summary the frontend sends (last route result)
  minerals / science sites    → aqueous-mineral sites (Ehlmann & Edwards 2014) + cited science cards
  Curiosity route             → data/curiosity_official_route.geojson (NASA JPL, approximate)
  temperature / radiation     → published REMS / RAD figures (app/weather_facts.py), never live
  sunlight / air / wind / dust→ cited GENERAL Mars facts (app/weather_facts.py), never local readings

Nothing is invented: when a value isn't in the app data or the cited facts, ARIA says so.
Confidence: high = app-calculated from HiRISE, medium = USGS gap fill or published past
measurements, low = general Mars facts, none = nothing available.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import aria_nlu as nlu
from . import aria_places as places
from . import aria_templates as tpl
from . import context as ctx
from . import weather_facts as wf
from .science import CARDS

MAX_SLOPE_DEG = 15.0       # router default (Apollo EVA traverses, EPSC2024)
CAUTION_SLOPE_DEG = 10.0   # router default (NASA MSL Engineering User Guide)
SECTOR_M = 500.0           # "is it safe to go north?" looks this far in that direction
SECTOR_HALF_ANGLE = 22.5   # ± degrees around the bearing (one compass point)
NEIGHBOURHOOD_M = 50.0
HAZARD_RADIUS_M = 250.0
MARS_R = 3396190.0
MOLA_RES_M = 463

DIRECTIONS = {
    "north": 0, "northeast": 45, "north-east": 45, "east": 90, "southeast": 135, "south-east": 135,
    "south": 180, "southwest": 225, "south-west": 225, "west": 270, "northwest": 315, "north-west": 315,
}
NICE_DIR = {"north": "north", "northeast": "north-east", "east": "east", "southeast": "south-east",
            "south": "south", "southwest": "south-west", "west": "west", "northwest": "north-west"}


# Location-specific questions, checked before topic words ("path", "clay", "temperature"…).
GO_TO_CLAY = re.compile(
    r"\b(path|route|way|go|get|walk|drive|navigate|take me|head|directions?|how do i reach|best)\b.*\b(clays?|yellowknife)\b"
    r"|\b(nearest|closest)\b.*\bclays?\b")
ROUTE_THERMAL = re.compile(
    r"\b(temperatures?|thermal|heat|hot|warm|cold|freezing)\b.*\b(path|route|traverse|trail|walk|way|trip)\b"
    r"|\b(path|route|traverse|trail|walk|way|trip)\b.*\b(temperatures?|thermal|heat|hot|warm|cold|freezing)\b")

# Coarse intent names kept for the API / frontend (backward compatible), per fine intent.
COARSE = {"temperature": "weather", "radiation": "weather", "wind": "weather", "pressure": "weather",
          "dust": "weather", "safety_here": "slope", "direction_safety": "slope", "route_danger": "route_safety",
          "route_length": "distance"}

# Answers that depend on where you are; a named place can stand in for the map centre.
LOCATION_INTENTS = ("safety_here", "direction_safety", "hazard", "elevation", "place_info", "minerals",
                    "science_sites", "go_to_clay", "curiosity_route")

SUGGESTIONS = ["Is it safe to travel north?", "What's the temperature at night compared to day?",
               "What's interesting near me?", "Does the sun appear in this region?"]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def detect_intent(message: str) -> str:
    """Coarse intent of a question (kept for callers and tests)."""
    m = message.lower()
    if GO_TO_CLAY.search(m):
        return "go_to_clay"
    if ROUTE_THERMAL.search(m):
        return "route_thermal"
    first = nlu.resolve(message).intents[0]
    return COARSE.get(first, first)


def detect_direction(message: str) -> tuple[str, float] | None:
    m = message.lower()
    for word in sorted(DIRECTIONS, key=len, reverse=True):   # "northeast" before "north"
        if re.search(rf"\b{re.escape(word)}\b", m):
            return word.replace("-", ""), float(DIRECTIONS[word])
    return None


def detect_place(message: str) -> dict | None:
    """A named place in the message (app/aria_places.py: Gale sites with typos allowed, IAU names exact)."""
    return places.find_place(message)


def great_circle_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * MARS_R * math.asin(math.sqrt(a))


def _fmt_pos(lon: float, lat: float) -> str:
    return f"{abs(lat):.4f}°{'S' if lat < 0 else 'N'}, {abs(lon):.4f}°{'W' if lon < 0 else 'E'}"


def _try_these(suggestions: list[str], lead: str = "Try one of these:") -> str:
    """The suggestions as plain text too, so they stay visible even where the buttons don't render."""
    return f"{lead} " + "; ".join(f"“{s}”" for s in suggestions) + "."


def _bearing_word(deg: float) -> str:
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][int(((deg % 360) + 22.5) // 45) % 8]


def _bearing_to(lon0: float, lat0: float, lon1: float, lat1: float) -> str:
    return _bearing_word(math.degrees(math.atan2((lon1 - lon0) * math.cos(math.radians(lat0)), lat1 - lat0)))


def _pct(frac: float) -> str:
    p = frac * 100
    return "0" if p == 0 else (f"{p:.1f}" if p < 1 else f"{p:.0f}")


def _grid_source(src: str) -> str:
    return ("COSMIC TRAIL slope analysis of the HiRISE DTM (5 m grid)" if src == "HiRISE DTM"
            else f"COSMIC TRAIL slope analysis of the {src} (5 m grid)")


@dataclass
class Part:
    """One answered intent: wording pieces + where the facts came from."""
    intent: str
    answer: str
    reason: str = ""
    tip: str = ""
    offer: str = ""
    sources: list[str] = field(default_factory=list)
    confidence: str = "none"
    data: dict[str, Any] = field(default_factory=dict)
    caveat: str | None = None
    suggestions: list[str] = field(default_factory=list)
    # Short dataset name for the API's `data_source` (backward compatible, e.g. "HiRISE DTM");
    # the full citation stays in `sources` and the reply's "Source:" line.
    short_source: str | None = None


_CONF = {"none": 0, "low": 1, "medium": 2, "high": 3}


class Assistant:
    def __init__(self, ds, context=None, minerals: dict | None = None):
        self.ds = ds               # TerrainDataset with a planetary CRS (None for fact-only questions)
        self.context = context     # TerrainContext (MOLA) or None
        self.minerals = minerals   # parsed data/minerals/aqueous_minerals.json or None

    # ---------- grid helpers ----------
    def _rc(self, lon: float, lat: float) -> tuple[int, int] | None:
        if self.ds is None or self.ds.proj is None:
            return None
        x, y = self.ds.proj.forward(lon, lat)
        return self.ds.grid.rc(x, y)

    def _source(self, r: int, c: int) -> str:
        if self.ds.usgs_filled is not None and self.ds.usgs_filled[r, c]:
            return "USGS Gale DEM (gap fill)"
        if self.ds.mola_filled is not None and self.ds.mola_filled[r, c]:
            return "MOLA 463 m (gap fill)"
        return "HiRISE DTM"

    def _window(self, r: int, c: int, radius_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = max(1, int(radius_m / self.ds.grid.cell))
        r0, r1 = max(0, r - n), min(self.ds.grid.height, r + n + 1)
        c0, c1 = max(0, c - n), min(self.ds.grid.width, c + n + 1)
        rr, cc = np.mgrid[r0:r1, c0:c1]
        inside = np.hypot(rr - r, cc - c) * self.ds.grid.cell <= radius_m
        return self.ds.slope[r0:r1, c0:c1], inside, np.stack([rr, cc])

    def _outside(self, lon: float, lat: float, what: str, seed: str) -> Part:
        data: dict[str, Any] = {"mola_resolution_m": MOLA_RES_M}
        reason, sources, conf = "", ["COSMIC TRAIL routing-grid coverage"], "none"
        if self.context is not None:
            h = float(self.context.sample(np.array([lon]), np.array([lat]))[0])
            data["elevation_m"] = round(h, 1)
            reason = (f"The coarse MOLA map puts the ground there at about {h:,.0f} m, but at {MOLA_RES_M} m per pixel "
                      "that's far too rough for walking decisions.")
            sources, conf = ["MOLA 463 m global DEM (NASA GSFC / USGS)"], "low"
        return Part("outside_grid",
                    f"That point is outside the 5 m routing grid, so I can't give {what} there.", reason,
                    "Move the map inside the dashed routable area, or name a place like Bradbury Landing.",
                    sources=sources, confidence=conf, data=data)

    def _dune_sentence(self, dune: dict) -> str:
        if not dune.get("loaded"):
            return "I couldn't check for dune sand because the dune map isn't loaded."
        if dune.get("inside"):
            return f"You're on {dune['name']} sand, so expect soft footing."
        if dune["distance_m"] <= ctx.NEAR_DUNE_M:
            return f"{dune['name']} sand starts about {dune['distance_m']} m away."
        return f"The nearest dune sand ({dune['name']}) is {dune['distance_m'] / 1000:.1f} km away."

    # ---------- safety at a point ----------
    def safety_here(self, lon: float, lat: float, seed: str) -> Part:
        rc = self._rc(lon, lat)
        if rc is None:
            return self._outside(lon, lat, "a slope check", seed)
        r, c = rc
        s, inside, _ = self._window(r, c, NEIGHBOURHOOD_M)
        vals = s[inside & np.isfinite(s)]
        here = float(self.ds.slope[r, c])
        src = self._source(r, c)
        if not vals.size or not math.isfinite(here):
            return Part("safety_here", "I can't tell the slope at this exact spot.",
                        "It's on the edge of the terrain grid, where slope can't be computed.",
                        "Move the map a little further inside the routable area and ask again.",
                        sources=[_grid_source(src)], confidence="low")
        above_c, above_m = int((vals > CAUTION_SLOPE_DEG).sum()), int((vals > MAX_SLOPE_DEG).sum())
        key = ("here.steep.answer" if here > MAX_SLOPE_DEG else "here.near.answer" if above_m
               else "here.caution.answer" if here > CAUTION_SLOPE_DEG or above_c else "here.gentle.answer")
        hs, hin, hidx = self._window(r, c, HAZARD_RADIUS_M)
        steep = hin & np.isfinite(hs) & (hs > MAX_SLOPE_DEG)
        nearest_steep = None
        if steep.any():
            rr, cc = hidx[0][steep], hidx[1][steep]
            dd = np.hypot(rr - r, cc - c) * self.ds.grid.cell
            k = int(np.argmin(dd))
            brg = math.degrees(math.atan2(cc[k] - c, -(rr[k] - r))) % 360
            nearest_steep = {"distance_m": round(float(dd[k])), "bearing": _bearing_word(brg)}
        dune = ctx.dune_status(lon, lat)
        reason = tpl.say(seed, "here.reason", here=f"{here:.1f}", r=f"{NEIGHBOURHOOD_M:.0f}", max=f"{vals.max():.1f}")
        reason += (f" The nearest ground over 15° is about {nearest_steep['distance_m']} m to the "
                   f"{nearest_steep['bearing']}." if nearest_steep
                   else f" There's no ground over 15° within {HAZARD_RADIUS_M:.0f} m.")
        reason += " " + self._dune_sentence(dune)
        sources = [_grid_source(src)] + ([f"dune outline ({dune['source']})"] if dune.get("loaded") and dune.get("source") else [])
        return Part("safety_here", tpl.pick(seed, key), reason, tpl.pick(seed, "here.tip"), sources=sources,
                    confidence="high" if src == "HiRISE DTM" else "medium", short_source=src,
                    data={"slope_deg": round(here, 2), "mean_deg": round(float(vals.mean()), 2),
                          "max_deg": round(float(vals.max()), 2), "cells_above_caution": above_c,
                          "cells_above_max": above_m, "nearest_steep": nearest_steep, "dunes": dune,
                          "data_quality": ctx.source_at(self.ds, r, c), "radius_m": NEIGHBOURHOOD_M,
                          "hazard_radius_m": HAZARD_RADIUS_M},
                    caveat="Judged on slope only, from a 5 m grid: boulders, loose sand and "
                           "small scarps are not resolved. Thresholds come from past missions, not a safety certification.")

    # ---------- safety in a direction (sector of the slope grid) ----------
    def sector(self, lon: float, lat: float, word: str) -> dict | None:
        """Slope statistics of the grid within SECTOR_M in one compass direction (± SECTOR_HALF_ANGLE)."""
        rc = self._rc(lon, lat)
        if rc is None:
            return None
        r, c = rc
        bearing = nlu.BEARINGS[word]
        cell = self.ds.grid.cell
        n = int(SECTOR_M / cell)
        r0, r1 = max(0, r - n), min(self.ds.grid.height, r + n + 1)
        c0, c1 = max(0, c - n), min(self.ds.grid.width, c + n + 1)
        rr, cc = np.mgrid[r0:r1, c0:c1]
        dx, dy = (cc - c) * cell, -(rr - r) * cell
        dist = np.hypot(dx, dy)
        ang = np.degrees(np.arctan2(dx, dy)) % 360
        diff = np.abs((ang - bearing + 180) % 360 - 180)
        in_sector = (dist > 0) & (dist <= SECTOR_M) & (diff <= SECTOR_HALF_ANGLE)
        s = self.ds.slope[r0:r1, c0:c1][in_sector]
        ok = np.isfinite(s)
        if ok.sum() < 10:
            return {"direction": word, "cells": int(ok.sum()), "insufficient": True}
        s = s[ok]
        expected = math.pi * SECTOR_M ** 2 * (2 * SECTOR_HALF_ANGLE / 360) / cell ** 2
        e = self.ds.elev[r0:r1, c0:c1][in_sector]
        far = (dist[in_sector] > 0.8 * SECTOR_M) & np.isfinite(e)
        here_e = float(self.ds.elev[r, c])
        dh = float(np.median(e[far]) - here_e) if far.any() and math.isfinite(here_e) else 0.0
        frac_c, frac_m = float((s > CAUTION_SLOPE_DEG).mean()), float((s > MAX_SLOPE_DEG).mean())
        verdict = "manageable" if frac_m == 0 and frac_c < 0.05 else ("some" if frac_m < 0.05 else "unsafe")
        x0, y0 = self.ds.proj.forward(lon, lat)
        b = math.radians(bearing)
        tx, ty = x0 + SECTOR_M * math.sin(b), y0 + SECTOR_M * math.cos(b)
        action = None
        if self.ds.grid.rc(tx, ty) is not None:
            tlon, tlat = self.ds.proj.inverse(tx, ty)
            action = {"type": "set_destination", "lon": round(tlon, 5), "lat": round(tlat, 5),
                      "label": f"{SECTOR_M:.0f} m {NICE_DIR[word]}"}
        return {"direction": word, "bearing_deg": bearing, "length_m": round(float(dist[in_sector][ok].max())),
                "radius_m": SECTOR_M, "cells": int(s.size), "coverage": round(min(1.0, s.size / expected), 2),
                "typical_deg": round(float(np.median(s)), 1), "mean_deg": round(float(s.mean()), 2),
                "max_deg": round(float(s.max()), 1), "pct_over_10": round(frac_c * 100, 1),
                "pct_over_15": round(frac_m * 100, 1), "frac_over_10": frac_c, "frac_over_15": frac_m,
                "elevation_change_m": round(dh, 1), "verdict": verdict, "action": action,
                "sources": sorted({self._source(int(a), int(b_)) for a, b_ in
                                   zip(rr[in_sector][ok][::25], cc[in_sector][ok][::25])})}

    def direction_safety(self, lon: float, lat: float, seed: str, directions: list[str]) -> Part:
        if self._rc(lon, lat) is None:
            return self._outside(lon, lat, "a direction check", seed)
        stats = [self.sector(lon, lat, d) for d in directions[:2]]
        good = [s for s in stats if s and not s.get("insufficient")]
        if not good:
            d = NICE_DIR[directions[0]]
            return Part("direction_safety", f"I can't judge the ground to the {d}: almost all of it is outside the "
                                            "detailed map.", "", "Move the map further inside the routable area and ask again.",
                        sources=["COSMIC TRAIL routing-grid coverage"], confidence="none", data={"direction": directions[0]})
        srcs = sorted({x for s in good for x in s["sources"]})
        source = " + ".join(_grid_source(x) for x in srcs) if srcs else _grid_source("HiRISE DTM")
        conf = "high" if srcs == ["HiRISE DTM"] else "medium"
        caveat = ("Straight-ahead sector, not a planned route. 5 m grid; thresholds from "
                  "past missions, not a safety certification.")
        if len(good) == 2:
            score = lambda s: (s["frac_over_15"], s["frac_over_10"], s["typical_deg"])
            best, other = sorted(good, key=score)
            same = score(best) == score(other)
            nb, no = NICE_DIR[best["direction"]], NICE_DIR[other["direction"]]
            answer = tpl.say(seed, "dir.compare.same" if same else "dir.compare.answer", best=nb.capitalize(), other=no)
            reason = tpl.say(seed, "dir.compare.reason", radius=f"{SECTOR_M:.0f}", best=nb, other=no,
                             b_typ=best["typical_deg"], b_max=best["max_deg"], b_pct=_pct(best["frac_over_10"]),
                             o_typ=other["typical_deg"], o_max=other["max_deg"], o_pct=_pct(other["frac_over_10"]))
            tip = tpl.pick(seed, f"dir.{best['verdict']}.tip")
            offer = tpl.say(seed, "dir.offer", radius=f"{SECTOR_M:.0f}", dir=nb) if best["action"] else ""
            return Part("direction_safety", answer, reason, tip, offer, [source], conf,
                        {"options": [best, other], "easier": best["direction"], "direction": best["direction"],
                         "length_m": best["length_m"], "elevation_change_m": best["elevation_change_m"],
                         "action": best["action"]}, caveat, short_source=" + ".join(srcs))
        s = good[0]
        d = NICE_DIR[s["direction"]]
        answer = tpl.say(seed, f"dir.{s['verdict']}.answer", dir=d)
        reason = tpl.say(seed, "dir.reason", radius=f"{SECTOR_M:.0f}", dir=d, typical=s["typical_deg"],
                         max=s["max_deg"], pct_caution=_pct(s["frac_over_10"]), pct_max=_pct(s["frac_over_15"]))
        if abs(s["elevation_change_m"]) >= 1:
            reason += f" The ground {'rises' if s['elevation_change_m'] > 0 else 'drops'} about " \
                      f"{abs(s['elevation_change_m']):.0f} m over that distance."
        if s["coverage"] < 0.6:
            reason += " Only part of that area is inside the detailed map, so this is a partial check."
        offer = tpl.say(seed, "dir.offer", radius=f"{SECTOR_M:.0f}", dir=d) if s["action"] else ""
        return Part("direction_safety", answer, reason, tpl.pick(seed, f"dir.{s['verdict']}.tip"), offer,
                    [source], conf, {**s, "action": s["action"]}, caveat, short_source=" + ".join(srcs))

    # ---------- hazards / elevation ----------
    def hazard(self, lon: float, lat: float, seed: str) -> Part:
        rc = self._rc(lon, lat)
        if rc is None:
            return self._outside(lon, lat, "a hazard check", seed)
        r, c = rc
        s, inside, idx = self._window(r, c, HAZARD_RADIUS_M)
        steep = inside & np.isfinite(s) & (s > MAX_SLOPE_DEG)
        n_steep = int(steep.sum())
        n_caution = int((inside & np.isfinite(s) & (s > CAUTION_SLOPE_DEG)).sum())
        data: dict[str, Any] = {"radius_m": HAZARD_RADIUS_M, "cells_above_max": n_steep, "cells_above_caution": n_caution}
        src = self._source(r, c)
        tip = "The 5 m map only shows slope, so loose sand, small rocks and dust aren't included."
        if n_steep == 0:
            answer = "I don't see any major slope hazards around you."
            reason = (f"Nothing within {HAZARD_RADIUS_M:.0f} m is steeper than the 15° walking limit"
                      + (f", although {n_caution} small patches are moderately steep (10–15°)." if n_caution else
                         ", and nothing is even over 10°."))
        else:
            rr, cc = idx[0][steep], idx[1][steep]
            d = np.hypot(rr - r, cc - c) * self.ds.grid.cell
            k = int(np.argmin(d))
            brg = math.degrees(math.atan2(cc[k] - c, -(rr[k] - r))) % 360
            here = float(self.ds.slope[r, c])
            on_steep = math.isfinite(here) and here > MAX_SLOPE_DEG
            smax = float(s[steep].max())
            data.update(nearest_steep_m=round(float(d[k])), nearest_steep_bearing=None if on_steep else _bearing_word(brg),
                        max_deg=round(smax, 1), on_steep_cell=on_steep, slope_here_deg=round(here, 1))
            if on_steep:
                answer = "Yes: you're standing on steep ground."
                reason = (f"This spot is {here:.1f}°, over the 15° limit, and {n_steep} map cells within "
                          f"{HAZARD_RADIUS_M:.0f} m are that steep (up to {smax:.1f}°).")
                tip = "Routes start from the nearest flatter ground, so move off this slope before setting out."
            else:
                answer = "There's steep ground nearby."
                reason = (f"The closest slope over 15° is about {d[k]:.0f} m to the {_bearing_word(brg)}, and the "
                          f"steepest ground within {HAZARD_RADIUS_M:.0f} m reaches {smax:.1f}°.")
                tip = "Planned routes go around it; on foot, give it a wide berth."
        return Part("hazard", answer, reason, tip, sources=[_grid_source(src)], short_source=src,
                    confidence="high" if src == "HiRISE DTM" else "medium", data=data,
                    caveat="Only slope is modelled (5 m grid).")

    def elevation(self, lon: float, lat: float, seed: str) -> Part:
        rc = self._rc(lon, lat)
        if rc is None:
            return self._outside(lon, lat, "a 5 m elevation", seed)
        r, c = rc
        e = float(self.ds.elev[r, c])
        src = self._source(r, c)
        if not math.isfinite(e):
            return Part("elevation", "I don't have an elevation for this exact spot.",
                        "This cell of the terrain grid has no height value.", sources=[_grid_source(src)])
        answer = (f"You're about {abs(e) / 1000:.1f} km {'below' if e < 0 else 'above'} Mars's reference level "
                  "(the areoid).")
        reason = (f"The ground here is at {e:,.0f} m relative to the areoid, which is normal for the floor of Gale "
                  "Crater, one of the lowest places near the Martian equator.")
        return Part("elevation", answer, reason, "Mount Sharp, in the middle of the crater, rises far above this floor.",
                    sources=[_grid_source(src).replace("slope analysis", "elevation")], short_source=src,
                    confidence="high" if src == "HiRISE DTM" else "medium", data={"elevation_m": round(e, 2)},
                    caveat="USGS gap-fill heights were adjusted to meet the HiRISE tiles (see SCIENTIFIC_LIMITATIONS.md)."
                    if src != "HiRISE DTM" else None)

    # ---------- route ----------
    def _no_route(self, what: str) -> Part:
        return Part(what, "You haven't planned a route yet, so there's nothing for me to check.",
                    tip="Set points A and B on the map and press Find Route, then ask me again.",
                    sources=["COSMIC TRAIL route planner (no route computed yet)"], confidence="none",
                    suggestions=["Is it safe to travel north?", "What's interesting near me?"])

    def route_danger(self, route: dict | None, seed: str) -> Part:
        if not route:
            return self._no_route("route_danger")
        caution = route.get("cells_above_caution") or 0
        segments, where = route.get("caution_segments"), route.get("caution_where")
        smax = route.get("slope_max_deg")
        length = route.get("surface_length_3d_m") or route.get("planimetric_length_m")
        gain = route.get("elevation_gain_m")
        near = f" near the {where}" if where in ("start", "middle", "end") else ""
        if caution:
            answer = f"Your route stays within the 15° walking limit, but it has some steeper stretches{near}."
        else:
            answer = "Your route looks gentle: the planner kept every step well under the 15° limit."
        bits = []
        if length:
            bits.append(f"it's {length / 1000:.2f} km long")
        if gain is not None:
            bits.append(f"climbs {gain:.0f} m")
        if smax is not None:
            bits.append(f"its steepest point is {smax:.1f}°")
        reason = (bits[0][0].upper() + bits[0][1:] + (", " + ", and ".join(bits[1:]) if len(bits) > 1 else "") + "."
                  if bits else "")
        if caution:
            n = segments or caution
            stretch = f"{segments} stretch{'es' if segments != 1 else ''}" if segments else f"{caution} map cells"
            reason += f" {stretch[0].upper() + stretch[1:]} {'are' if n != 1 else 'is'} between 10° and 15°{near}."
        thermal = route.get("thermal") or {}
        if thermal.get("crossings"):
            reason += f" It also crosses {', '.join(thermal.get('dunes') or ['dune sand'])}, which needs extra care."
        cov = route.get("data_coverage_on_route")
        return Part("route_danger", answer, reason,
                    "The 5 m map can't see boulders or loose sand, so treat this as a planning aid, not a safety guarantee.",
                    sources=["COSMIC TRAIL route planner (HiRISE DTM + USGS gap fill, 5 m grid)"], confidence="high",
                    data={k: route.get(k) for k in ("mode", "cells", "slope_max_deg", "slope_mean_deg",
                                                    "cells_above_caution", "caution_segments", "surface_length_3d_m",
                                                    "planimetric_length_m", "elevation_gain_m", "elevation_loss_m",
                                                    "data_coverage_on_route")},
                    caveat="Judged on slope from a 5 m grid; the router never crosses ground over 15°. Not a statement "
                           "about operational safety." + (f" Data coverage on route: {cov * 100:.0f}%."
                                                          if isinstance(cov, (int, float)) else ""))

    def route_length(self, route: dict | None, seed: str) -> Part:
        if not route or not (route.get("surface_length_3d_m") or route.get("planimetric_length_m")):
            return self._no_route("route_length")
        L = route.get("surface_length_3d_m") or route["planimetric_length_m"]
        flat = route.get("planimetric_length_m") or L
        return Part("route_length", f"Your route is {L / 1000:.2f} km long.",
                    f"That's measured along the ground, including the ups and downs; on the flat map it's {flat / 1000:.2f} km.",
                    "I don't have a walking-speed model, so I can't tell you how long it would take to walk.",
                    sources=["COSMIC TRAIL route planner (HiRISE DTM + USGS gap fill, 5 m grid)"], confidence="high",
                    data={"distance_m": L, "planimetric_length_m": flat})

    def distance(self, lon: float, lat: float, message: str, route: dict | None, seed: str) -> Part:
        place = detect_place(message)
        if place and (abs(place["lon"] - lon) > 1e-4 or abs(place["lat"] - lat) > 1e-4):
            d = great_circle_m(lon, lat, place["lon"], place["lat"])
            return Part("distance", f"{place['name']} is about {d / 1000:.1f} km away in a straight line.",
                        f"That's the great-circle distance from the centre of your map ({_fmt_pos(lon, lat)}); a "
                        "walkable route will be longer.",
                        "Set it as destination B and press Find Route to see the real path.",
                        sources=[place["source"]],
                        confidence="high", data={"distance_m": round(d), "to": place["name"],
                                                 "from": {"lon": lon, "lat": lat}})
        if route and route.get("surface_length_3d_m"):
            p = self.route_length(route, seed)
            p.intent = "distance"
            return p
        return Part("distance", "Distance to where? I need a place or a planned route.",
                    "I know the coordinates of places like Bradbury Landing, Mount Sharp and Aeolis Palus, and I can "
                    "measure a route once you've planned one.",
                    "Try “How far is Mount Sharp?”, or set A and B and press Find Route.",
                    sources=["COSMIC TRAIL science cards"], confidence="none",
                    suggestions=["How far is Mount Sharp?", "How long is my route?"])

    def route_thermal(self, lon: float, lat: float, route: dict | None, seed: str) -> Part:
        """Thermal risk along the planned route: does it cross dune sand (data/hazard_zones.geojson)?"""
        notes = ctx.dune_notes()
        note = notes[0]["note"] if notes else None
        srcs = sorted({s for n in notes for s in (n.get("temperature_source"), n.get("source")) if s})
        source = "dune outline (data/hazard_zones.geojson)" + (f"; {'; '.join(srcs)}" if srcs else "")
        caveat = "Dune outline is approximate. Temperatures are published figures, not live data."
        thermal = (route or {}).get("thermal")
        if not route:
            st = ctx.dune_status(lon, lat)
            if not st["loaded"]:
                return Part("route_thermal", "I can't check dune sand here because the dune map isn't loaded.",
                            sources=["COSMIC TRAIL (dune map missing)"], confidence="none")
            answer = (f"This spot is on {st['name']} sand, so the thermal risk is HIGH." if st["inside"] else
                      f"This spot is off the dunes, about {st['distance_m'] / 1000:.1f} km from {st['name']}.")
            return Part("route_thermal", answer, note or "", "Press Find Route, then ask again and I'll check the whole path.",
                        sources=[source], confidence="medium", data={"dunes": st, "note": note}, caveat=caveat)
        if not thermal:
            return Part("route_thermal", "I need a fresh route to check that.",
                        "This route was computed without the dune-crossing check.",
                        "Press Find Route again, then ask me once more.", sources=["COSMIC TRAIL route planner"])
        if not thermal.get("checked"):
            return Part("route_thermal", "I couldn't check dune crossings on this route because the dune map isn't loaded.",
                        sources=["COSMIC TRAIL (dune map missing)"], data={"thermal": thermal})
        if thermal.get("crossings"):
            names = ", ".join(thermal.get("dunes") or ["dune sand"])
            frac = thermal.get("fraction")
            share = f" (about {frac * 100:.0f}% of the route)" if isinstance(frac, (int, float)) else ""
            return Part("route_thermal", f"This path has HIGH thermal risk: it crosses {names}{share}.", note or "",
                        "Plan the dune crossing for the morning, or move A/B to route around the sand.",
                        sources=[source], confidence="medium", data={"thermal": thermal, "note": note}, caveat=caveat)
        return Part("route_thermal", "This path has LOW thermal risk because it stays off the dunes.",
                    f"For reference: {note}" if note else "", sources=[source], confidence="medium",
                    data={"thermal": thermal, "note": note}, caveat=caveat)

    # ---------- minerals / places / science ----------
    def minerals_near(self, lon: float, lat: float, seed: str) -> Part:
        data: dict[str, Any] = {}
        clay = ctx.nearest_confirmed_clay(lon, lat)
        data["nearest_confirmed_clay"] = {k: clay[k] for k in ("name", "distance_m", "bearing")}
        answer = (f"The closest confirmed clay site is {clay['name']}, about {clay['distance_m'] / 1000:.1f} km to the "
                  f"{clay['bearing']}, where Curiosity found {clay['mineral']}.")
        reason = ""
        sources = [f"Curiosity results ({clay['source']})"]
        pts = (self.minerals or {}).get("points") or []
        if pts:
            labels = {l["class"]: l["label"] for l in self.minerals.get("legend", [])}
            ranked = sorted(((great_circle_m(lon, lat, p["lon"], p["lat"]), p) for p in pts), key=lambda t: t[0])
            within = sum(1 for d, _ in ranked if d <= 150_000)
            d0, p0 = ranked[0]
            reason = (f"From orbit, the nearest {labels.get(p0['c'], p0['c']).split(' (')[0].lower()} detection is about "
                      f"{d0 / 1000:.0f} km to the {_bearing_to(lon, lat, p0['lon'], p0['lat'])}, and there are "
                      f"{within} detection sites within 150 km.")
            data["nearest_sites"] = [{"class": p["c"], "distance_km": round(d / 1000, 1), "lon": p["lon"], "lat": p["lat"]}
                                     for d, p in ranked[:3]]
            data["sites_within_150km"] = within
            sources.insert(0, "CRISM/OMEGA/THEMIS detection sites (Ehlmann & Edwards 2014)")
        data["action"] = {"type": "set_destination", "lon": clay["lon"], "lat": clay["lat"], "label": clay["name"]}
        return Part("minerals", answer, reason,
                    "Clays mean water once flowed here; that's evidence of a habitable past, not of life.",
                    f"Want me to set {clay['name']} as your destination?", sources, "medium", data,
                    caveat="Orbital detection sites are points (±~0.01°), not a mineral map.")

    def go_to_clay(self, lon: float, lat: float, seed: str) -> Part:
        site = ctx.nearest_confirmed_clay(lon, lat)
        action = {"type": "set_destination", "lon": site["lon"], "lat": site["lat"], "label": site["name"]}
        data: dict[str, Any] = {"target": {k: site[k] for k in ("name", "lon", "lat", "distance_m", "bearing")},
                                "action": action}
        src = f"Curiosity results ({site['source']})"
        if site["distance_m"] < 50:
            return Part("go_to_clay", f"You're at {site['name']}.", f"Curiosity confirmed {site['mineral']} here "
                        f"({site['how']}).", sources=[src], confidence="medium", data=data)
        km = site["distance_m"] / 1000
        prof = (ctx.line_profile(self.ds, lon, lat, site["lon"], site["lat"])
                if self.ds is not None and self.ds.proj else {"sampled": 0})
        data["terrain_between"] = prof
        if not prof.get("sampled"):
            terrain = "The ground in between is outside the 5 m map, so I can't check it."
        else:
            feel = ctx.terrain_word(prof["mean_deg"]).replace("Flat plain", "mostly flat ground").lower()
            n = prof["steep_sections"]
            terrain = (f"The straight line there crosses {feel} with no steep sections." if n == 0 else
                       f"The straight line there crosses {feel}, with {n} steep section{'s' if n != 1 else ''} "
                       f"(steepest {prof['max_deg']:.0f}°, {ctx.where_word(prof['steepest_at'])}).")
            if prof["covered_fraction"] < 0.95:
                terrain += f" Only {prof['covered_fraction'] * 100:.0f}% of the line is inside the 5 m map."
        return Part("go_to_clay", f"{site['name']} is about {km:.1f} km {site['bearing']} of you, and Curiosity "
                                  f"confirmed {site['mineral']} there.", terrain,
                    "Tap “Set as Destination B”, then press Find Route for a path that avoids steep ground.",
                    sources=[src, "COSMIC TRAIL line check on the HiRISE DTM"], confidence="medium", data=data,
                    caveat="Straight-line check from your position, not a planned route. Position approximate.")

    def place_info(self, lon: float, lat: float, seed: str) -> Part:
        rc = self._rc(lon, lat)
        unit = ctx.geologic_unit(lon, lat)
        orb = ctx.nearest_orbital_mineral(lon, lat, self.minerals)
        clay = ctx.nearest_confirmed_clay(lon, lat)
        data: dict[str, Any] = {"geologic_unit": unit, "nearest_orbital_mineral": orb,
                                "nearest_confirmed_clay": {k: clay[k] for k in ("name", "distance_m", "bearing")}}
        unit_txt = (f"this is the {unit['unit']} geologic unit ({unit['age_word']}, approximate map)" if unit
                    else "this is outside the mapped geologic units")
        clay_txt = (f"the nearest confirmed clays are at {clay['name']}, {clay['distance_m'] / 1000:.1f} km to the "
                    f"{clay['bearing']}" if clay["distance_m"] >= 50 else f"you're at {clay['name']}, where clays were confirmed")
        sources = ["USGS SIM 3292 geologic map (simplified)", f"Curiosity results ({clay['source']})"]
        if orb:
            sources.append("CRISM/OMEGA/THEMIS detection sites (Ehlmann & Edwards 2014)")
        if rc is None:
            data["hirise_coverage"] = False
            return Part("place_info", "You're outside the detailed 5 m map, so I only have coarse information here.",
                        f"Geologically, {unit_txt}, and {clay_txt}. HiRISE coverage: no.",
                        "Move inside the dashed routable area for detailed terrain answers.",
                        sources=sources, confidence="low", data=data)
        r, c = rc
        e = float(self.ds.elev[r, c])
        s_, inside, _ = self._window(r, c, NEIGHBOURHOOD_M)
        vals = s_[inside & np.isfinite(s_)]
        src = self._source(r, c)
        hirise = src == "HiRISE DTM"
        dune = ctx.dune_status(lon, lat)
        kind = "dune sand" if dune.get("inside") else ctx.terrain_word(float(vals.mean()) if vals.size else 0.0).lower()
        data.update(elevation_m=round(e, 1), terrain=kind, hirise_coverage=hirise, data_source=src, dunes=dune,
                    mean_slope_deg=round(float(vals.mean()), 1) if vals.size else None)
        orb_txt = (f" From orbit, {orb['label'].split(' (')[0].lower()} was detected about "
                   f"{orb['distance_m'] / 1000:.0f} km to the {orb['bearing']}." if orb else "")
        return Part("place_info", f"You're on {kind} at about {e:,.0f} m elevation.",
                    f"Geologically, {unit_txt}, and {clay_txt}.{orb_txt} "
                    f"HiRISE coverage here: {'yes' if hirise else 'no (USGS gap fill)'}.",
                    "Ask me what's interesting nearby, or whether it's safe to head in a particular direction.",
                    sources=[_grid_source(src).replace("slope analysis", "terrain")] + sources,
                    confidence="high" if hirise else "medium", data=data,
                    caveat="Elevation relative to the Mars areoid; unit polygons are simplified.")

    def science_sites(self, lon: float, lat: float, seed: str) -> Part:
        sites = [{"name": c.site, "lon": c.lon, "lat": c.lat, "summary": c.summary, "card": True}
                 for c in CARDS if c.lon is not None]
        for s in ctx.CONFIRMED_CLAY_SITES:
            sites.append({"name": s["name"], "lon": s["lon"], "lat": s["lat"],
                          "summary": f"Curiosity confirmed {s['mineral']} here.", "source": s["source"]})
        for d in sites:
            d["distance_m"] = round(great_circle_m(lon, lat, d["lon"], d["lat"]))
            d["bearing"] = _bearing_to(lon, lat, d["lon"], d["lat"])
        sites.sort(key=lambda d: d["distance_m"])
        top = sites[:3]
        first = top[0]
        where = ("right where you are" if first["distance_m"] < 100 else
                 f"about {first['distance_m'] / 1000:.1f} km to the {first['bearing']}")
        answer = f"The closest science site to you is {first['name']}, {where}."
        reason = first["summary"].rstrip(".") + "."
        if len(top) > 1:
            reason += " Also nearby: " + " and ".join(f"{d['name']} ({d['distance_m'] / 1000:.1f} km {d['bearing']})"
                                                      for d in top[1:]) + "."
        action = {"type": "set_destination", "lon": first["lon"], "lat": first["lat"], "label": first["name"]}
        far = first["distance_m"] >= 100
        return Part("science_sites", answer, reason, "Turn on the Science sites layer to see them all on the map.",
                    f"Want me to set {first['name']} as your destination?" if far else "",
                    sources=["COSMIC TRAIL science cards (" + ", ".join(d["name"] for d in top if d.get("card"))
                             + "; each card lists its citations)"]
                            + [f"Curiosity results ({d['source']})" for d in top if d.get("source")],
                    confidence="medium", data={"sites": top, "action": action if far else None})

    def curiosity_route(self, lon: float, lat: float, seed: str) -> Part:
        try:
            f = json.loads((DATA_DIR / "curiosity_official_route.geojson").read_text(encoding="utf-8"))["features"][0]
            wps = f["properties"]["waypoints"]
            url = f["properties"].get("url", "")
        except (OSError, KeyError, IndexError, ValueError):
            return Part("curiosity_route", "I don't have Curiosity's route loaded right now.",
                        sources=["COSMIC TRAIL (Curiosity route file missing)"])
        for w in wps:
            w["distance_m"] = round(great_circle_m(lon, lat, w["lon"], w["lat"]))
        near = min(wps, key=lambda w: w["distance_m"])
        where = (f"You're right at {near['name']}, one of its waypoints." if near["distance_m"] < 100 else
                 f"The closest one to you is {near['name']}, about {near['distance_m'] / 1000:.1f} km to the "
                 f"{_bearing_to(lon, lat, near['lon'], near['lat'])}.")
        return Part("curiosity_route",
                    f"Curiosity's planned path climbs from {wps[0]['name']} towards {wps[-1]['name']} on the slopes of "
                    "Mount Sharp.",
                    f"It has {len(wps)} waypoints: {', '.join(w['name'] for w in wps)}. {where}",
                    "Turn on the Curiosity route layer to see the path; the waypoints are approximate.",
                    sources=["NASA JPL, Curiosity's Proposed Path up Mount Sharp" + (f" ({url})" if url else "")],
                    confidence="medium", data={"waypoints": wps, "waypoint_count": len(wps), "nearest": near["name"]})

    def data_sources(self, lon: float, lat: float, seed: str) -> Part:
        meta = getattr(self.ds, "meta", None) or {}
        tiles = meta.get("tiles_merged") or []
        fill = (meta.get("usgs_fill") or {}).get("source") or "USGS MSL Gale DEM"
        cell = getattr(getattr(self.ds, "grid", None), "cell", None)
        rc = self._rc(lon, lat)
        here = self._source(*rc) if rc else None
        answer = "My terrain answers come from NASA's HiRISE elevation models of Gale Crater."
        reason = (f"COSMIC TRAIL merges {len(tiles)} HiRISE DTMs into a {cell:.0f} m grid, fills their gaps with the "
                  f"{fill}, and uses MOLA heights for the wider globe." if tiles and cell else
                  "COSMIC TRAIL builds its terrain grid from HiRISE DTMs, with USGS and MOLA data filling the gaps.")
        if here:
            reason += f" At the centre of your map the ground comes from the {here}."
        return Part("data_sources", answer, reason,
                    "Temperatures and radiation come from published Curiosity measurements, not live data.",
                    sources=["COSMIC TRAIL dataset metadata" + (f" ({', '.join(t.split('.')[0] for t in tiles)})" if tiles else "")],
                    confidence="high" if tiles else "medium",
                    data={"tiles_merged": tiles, "tile_count": len(tiles), "cell_m": cell, "fill_source": fill,
                          "source_here": here})

    # ---------- environment (published past measurements or general facts) ----------
    def temperature(self, seed: str, time: str | None, compare: bool) -> Part:
        mode = "both" if compare or time == "both" else (time or "general")
        f = {"high": wf.AIR_TEMP_HIGH_C, "low": wf.AIR_TEMP_LOW_C, "period": wf.AIR_TEMP_PERIOD,
             "swing": wf.AIR_TEMP_HIGH_C - wf.AIR_TEMP_LOW_C}
        return Part("temperature", tpl.pick(seed, f"temp.{mode}.answer"), tpl.say(seed, f"temp.{mode}.reason", **f),
                    tpl.say(seed, f"temp.{mode}.tip", **f),
                    sources=[f"{wf.AIR_TEMP_SOURCE} (REMS air temperature, Curiosity)"], confidence="medium",
                    data={"air_temp_high_c": wf.AIR_TEMP_HIGH_C, "air_temp_low_c": wf.AIR_TEMP_LOW_C,
                          "swing_c": f["swing"], "period": wf.AIR_TEMP_PERIOD, "mode": mode,
                          "source_url": wf.AIR_TEMP_URL},
                    caveat=f"Published figures for {wf.AIR_TEMP_PERIOD}, not live weather and not a forecast. Ground "
                           "temperature differs from air temperature and changes with season and place.")

    def radiation(self, seed: str) -> Part:
        return Part("radiation", tpl.pick(seed, "rad.answer"),
                    tpl.say(seed, "rad.reason", dose=wf.RADIATION_MSV_PER_DAY, src=wf.RADIATION_SOURCE),
                    tpl.pick(seed, "rad.tip"), sources=[f"{wf.RADIATION_SOURCE} (RAD on Curiosity)"],
                    confidence="medium", data={"radiation_msv_per_day": wf.RADIATION_MSV_PER_DAY},
                    caveat="Published figure, not live data; radiation varies with solar activity and season.")

    def _no_reading(self, seed: str, intent: str, general: str, source: str) -> Part:
        """Wind / pressure / dust: no local readings are loaded — say so, then only cited general facts."""
        return Part(intent, tpl.pick(seed, f"{intent}.answer"), general, tpl.pick(seed, f"{intent}.tip"),
                    sources=[source], confidence="low", data={"measurement_loaded": False},
                    caveat="General knowledge, not a measurement at this location. Do not use for planning.")

    def wind(self, seed: str) -> Part:
        return self._no_reading(seed, "wind", wf.WIND_GENERAL, f"{wf.MARS_FACTS_SOURCE}; no local wind data loaded")

    def pressure(self, seed: str) -> Part:
        p = self._no_reading(seed, "pressure", wf.PRESSURE_GENERAL,
                             f"{wf.MARS_FACTS_SOURCE}; no local pressure data loaded")
        p.data.update(air_co2_pct=wf.AIR_CO2_PCT, pressure_pct_of_earth_below=wf.AIR_PRESSURE_PCT_OF_EARTH_MAX)
        return p

    def dust(self, seed: str) -> Part:
        return self._no_reading(seed, "dust", wf.DUST_STORM_GENERAL, f"{wf.DUST_STORM_SOURCE}; no local dust data loaded")

    def sunlight(self, seed: str) -> Part:
        return Part("sunlight", tpl.pick(seed, "sun.answer"),
                    tpl.say(seed, "sun.reason", h=wf.SOL_HOURS, m=wf.SOL_MINUTES), tpl.pick(seed, "sun.tip"),
                    sources=[wf.MARS_FACTS_SOURCE], confidence="low",
                    data={"sol_hours": wf.SOL_HOURS, "sol_minutes": wf.SOL_MINUTES, "source_url": wf.MARS_FACTS_URL},
                    caveat="General Mars knowledge, not a live sunlight or dust reading at this location.")

    def survival(self, seed: str, danger: bool = False) -> Part:
        air = wf.PRESSURE_GENERAL.replace(", far too thin to breathe or to survive without a pressurised suit", "")
        return Part("survival", tpl.pick(seed, "survival.danger.answer" if danger else "survival.answer"),
                    tpl.say(seed, "survival.reason", air=air, low=wf.AIR_TEMP_LOW_C, dose=wf.RADIATION_MSV_PER_DAY),
                    tpl.pick(seed, "survival.tip"),
                    sources=[f"{wf.AIR_TEMP_SOURCE} (REMS, Curiosity)", f"{wf.RADIATION_SOURCE} (RAD on Curiosity)",
                             wf.MARS_FACTS_SOURCE], confidence="medium",
                    data={"air_temp_low_c": wf.AIR_TEMP_LOW_C, "radiation_msv_per_day": wf.RADIATION_MSV_PER_DAY,
                          "air_co2_pct": wf.AIR_CO2_PCT, "pressure_pct_of_earth_below": wf.AIR_PRESSURE_PCT_OF_EARTH_MAX},
                    caveat=f"Temperatures and radiation are published figures ({wf.AIR_TEMP_PERIOD}), not live data. "
                           "General guidance, not a safety assessment.")

    # No data is used in these replies, so they carry no Source line and no data-source badge.
    def greeting(self, seed: str) -> Part:
        return Part("greeting", tpl.pick(seed, "greeting.answer"), tpl.pick(seed, "greeting.reason"),
                    _try_these(SUGGESTIONS, "Here are a few things you can ask me:"), suggestions=SUGGESTIONS)

    def unknown(self, seed: str) -> Part:
        return Part("unknown", tpl.pick(seed, "unknown.answer"), tpl.pick(seed, "unknown.reason"),
                    _try_these(SUGGESTIONS), suggestions=SUGGESTIONS)

    def unknown_place(self, name: str) -> Part:
        known = places.known_place_names()
        sugg = [f"It's near {known[0]}", f"What about {known[1]}?", f"Am I safe at {known[2]}?"]
        return Part("unknown_place", f"I don't have “{name}” in my place list, so I can't use it as your position.",
                    f"Places I do know around Gale Crater: {', '.join(known[:-1])} and {known[-1]}. I also know the "
                    "IAU-named features on the globe, by their exact name.",
                    _try_these(sugg), data={"unknown_place": name, "known_places": known}, suggestions=sugg)

    # ---------- entry point ----------
    def answer(self, message: str, lon: float, lat: float, route: dict | None = None,
               previous: dict | None = None) -> dict:
        """previous: {"topic": fine intent of ARIA's last answer, "message": the user's last question}."""
        seed = nlu.normalize(message)
        m = message.lower()
        prev = None
        if previous and previous.get("topic"):
            prev = {"topic": previous["topic"],
                    "directions": nlu.understand(previous.get("message") or "").directions}
        follow = False
        if GO_TO_CLAY.search(m):
            intents, parse = ["go_to_clay"], nlu.understand(message)
        elif ROUTE_THERMAL.search(m):
            intents, parse = ["route_thermal"], nlu.understand(message)
        else:
            res = nlu.resolve(message, prev)
            intents, parse, follow = res.intents, res.parse, res.follow_up
        directions = parse.directions or (prev or {}).get("directions") or []

        # ---- a named place as the position ("it's near Pahrump Hills", "what about Yellowknife Bay?")
        place = detect_place(message)
        if place and place.get("region") and re.search(r"\bhere\b", m):
            place = None                                    # "am I safe here in Gale Crater?" → keep the map point
        prev_topic = (prev or {}).get("topic")
        if place:
            location_prev = prev_topic in LOCATION_INTENTS or prev_topic == "distance"
            if intents == ["unknown"] or (follow and not location_prev):
                # Only a place was given: answer the previous question there, or describe the place.
                intents = [prev_topic] if location_prev else ["place_info"]
        else:
            name = places.unknown_place_name(message)
            if name and (intents == ["unknown"] or intents[0] in LOCATION_INTENTS or follow):
                return self._combine([self.unknown_place(name)], lon, lat)
        used_place = None
        if place and intents[0] in LOCATION_INTENTS and not (
                intents[0] == "go_to_clay" and any(s["name"] == place["name"] for s in ctx.CONFIRMED_CLAY_SITES)):
            lon, lat = place["lon"], place["lat"]           # analyse at the named place
            used_place = place

        handlers = {
            "safety_here": lambda: self.safety_here(lon, lat, seed),
            "direction_safety": lambda: (self.direction_safety(lon, lat, seed, directions) if directions
                                         else self.safety_here(lon, lat, seed)),
            "hazard": lambda: self.hazard(lon, lat, seed),
            "elevation": lambda: self.elevation(lon, lat, seed),
            "route_danger": lambda: self.route_danger(route, seed),
            "route_length": lambda: self.route_length(route, seed),
            "distance": lambda: self.distance(lon, lat, message, route, seed),
            "route_thermal": lambda: self.route_thermal(lon, lat, route, seed),
            "minerals": lambda: self.minerals_near(lon, lat, seed),
            "go_to_clay": lambda: self.go_to_clay(lon, lat, seed),
            "place_info": lambda: self.place_info(lon, lat, seed),
            "science_sites": lambda: self.science_sites(lon, lat, seed),
            "curiosity_route": lambda: self.curiosity_route(lon, lat, seed),
            "data_sources": lambda: self.data_sources(lon, lat, seed),
            "temperature": lambda: self.temperature(seed, parse.time, parse.compare),
            "radiation": lambda: self.radiation(seed),
            "wind": lambda: self.wind(seed),
            "pressure": lambda: self.pressure(seed),
            "dust": lambda: self.dust(seed),
            "sunlight": lambda: self.sunlight(seed),
            "survival": lambda: self.survival(seed, danger="safety" in parse.topics),
            "greeting": lambda: self.greeting(seed),
        }
        parts = [handlers.get(i, lambda: self.unknown(seed))() for i in intents]
        if used_place:
            p = parts[0]
            name = re.sub(r"\s*\(.*\)", "", used_place["name"])
            pos = _fmt_pos(used_place["lon"], used_place["lat"]) + (", approximate" if used_place["approximate"] else "")
            p.answer = f"Using {name} ({pos}) as your position. {p.answer}"
            offer = f"Want me to move the map to {name}?"
            p.offer = f"{p.offer} {offer}".strip() if p.offer else offer
            p.sources = p.sources + [f"Position of {name}: {used_place['source']}"]
            p.data["place"] = {k: used_place.get(k) for k in ("name", "lon", "lat", "approximate", "source", "match")}
            p.data["move_map"] = {"type": "move_map", "lon": used_place["lon"], "lat": used_place["lat"], "label": name}
        return self._combine(parts, lon, lat)

    def _combine(self, parts: list[Part], lon: float, lat: float) -> dict:
        sources = list(dict.fromkeys(s for p in parts for s in p.sources))
        if len(parts) == 1:
            p = parts[0]
            text = tpl.compose(p.answer, p.reason, p.tip, p.offer, "; ".join(p.sources))
            data = dict(p.data)
        else:   # several topics in one question: one paragraph each, one Source line
            paras = [" ".join(x for x in (p.answer, p.reason, p.tip) if x) for p in parts]
            text = "\n\n".join(paras) + (f"\n\nSource: {'; '.join(sources)}" if sources else "")
            data = {}
            for p in parts:
                data.update(p.data)
            data["topics"] = [p.intent for p in parts]
        conf = min((p.confidence for p in parts), key=lambda c: _CONF[c])
        first = parts[0]
        intent = COARSE.get(first.intent, first.intent)
        if all(COARSE.get(p.intent) == "weather" for p in parts):
            intent = "weather"
        suggestions = list(dict.fromkeys(s for p in parts for s in p.suggestions))
        caveats = [p.caveat for p in parts if p.caveat]
        data_source = " + ".join(dict.fromkeys(s for p in parts if (s := p.short_source or " + ".join(p.sources))))
        return {"reply": text, "data_source": data_source, "confidence": conf, "intent": intent,
                "topic": first.intent, "topics": [p.intent for p in parts],
                "location": {"lon": lon, "lat": lat}, "data": data,
                "caveat": " ".join(dict.fromkeys(caveats)) or None, "sources": sources, "suggestions": suggestions,
                "engine": "rule-based (no language model, offline)"}
