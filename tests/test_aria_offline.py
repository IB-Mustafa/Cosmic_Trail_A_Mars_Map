"""ARIA offline conversation tests: varied wording, typos, multi-intent questions, follow-ups,
the unknown fallback, the reply shape ("Source:" last) and a check that no reply contains a
number that isn't in the app data or app/weather_facts.py.
"""
from __future__ import annotations

import re

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import assistant as A
from app import weather_facts as wf
from app.aria_nlu import normalize, resolve

pytestmark = pytest.mark.asyncio

REAL_DS = "hirise_gale"
BRADBURY = (137.4417, -4.5895)


@pytest_asyncio.fixture(scope="module")
async def client():
    from app.main import app, _load_datasets, DATASETS
    if not DATASETS:
        _load_datasets()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(scope="module")
def aria():
    from app import main
    if not main.DATASETS:
        main._load_datasets()
    if REAL_DS not in main.DATASETS:
        pytest.skip(f"{REAL_DS} dataset not present")
    return A.Assistant(main.DATASETS[REAL_DS], main.TERRAIN_CONTEXT, main._minerals_data())


def ask(aria, q, previous=None, route=None, at=BRADBURY):
    return aria.answer(q, *at, route=route, previous=previous)


# ---------------------------------------------------------------------------
# Varied wording (at least 5 phrasings per required intent)
# ---------------------------------------------------------------------------
DAY_NIGHT = ["whats the temperature at night as compared to day",
             "How much colder is it at night than during the day?",
             "day vs night temperature?",
             "difference between day and night temps",
             "how does the temperature change from day to night"]
WIND = ["what about wind??", "Is it windy here?", "how strong are the winds", "wind speed?",
        "will the wind blow me over"]
SUNLIGHT = ["does sun appear and is there sunlight in this region ever?", "Does the sun appear in this region?",
            "is there daylight here", "how long is a day on mars", "when does the sun rise here"]
NORTH = ["Is it safe to travel north?", "can i walk north safely", "is going north dangerous",
         "should i head north", "how is the terrain to the north"]


@pytest.mark.parametrize("q", DAY_NIGHT)
async def test_day_vs_night_temperature_is_answered_as_a_comparison(aria, q):
    d = ask(aria, q)
    assert d["topic"] == "temperature" and d["data"]["mode"] == "both", q
    assert "0 °C" in d["reply"] and "-70 °C" in d["reply"] and "70 °C" in d["reply"].replace("-70 °C", "")
    assert re.search(r"\bnight", d["reply"].lower()) and re.search(r"\bday", d["reply"].lower())
    assert "thermal protection" in d["reply"]
    assert d["confidence"] == "medium" and "PIA16913" in d["reply"].split("\n")[-1]


@pytest.mark.parametrize("q", WIND)
async def test_wind_says_no_reading_and_only_wind_facts(aria, q):
    d = ask(aria, q)
    assert d["topic"] == "wind", q
    assert re.search(r"(don't have|no) wind", d["reply"].lower())
    assert "radiation" not in d["reply"].lower() and "°c" not in d["reply"].lower()   # nothing unrelated
    assert d["confidence"] == "low" and d["data"]["measurement_loaded"] is False
    assert not re.search(r"\b\d+(\.\d+)?\s*(m/s|km/h|mph)", d["reply"])               # no invented speed


@pytest.mark.parametrize("q", SUNLIGHT)
async def test_sunlight_questions_get_a_yes_with_the_sol_length(aria, q):
    d = ask(aria, q)
    assert d["topic"] == "sunlight", q
    assert d["reply"].startswith("Yes")
    assert f"{wf.SOL_HOURS} hours and {wf.SOL_MINUTES} minutes" in d["reply"]
    assert "dust" in d["reply"].lower() and d["confidence"] == "low"
    assert "NASA Mars Fact Sheet" in d["reply"].split("\n")[-1]


@pytest.mark.parametrize("q", NORTH)
async def test_directional_safety_is_computed_from_the_slope_grid(aria, q):
    d = ask(aria, q)
    assert d["topic"] == "direction_safety" and d["data"]["direction"] == "north", q
    s = aria.sector(*BRADBURY, "north")
    assert d["data"]["max_deg"] == s["max_deg"] and d["data"]["typical_deg"] == s["typical_deg"]
    assert f"{s['max_deg']}°" in d["reply"] and f"{s['typical_deg']}°" in d["reply"]   # numbers in the reason
    assert "15°" in d["reply"] and s["cells"] > 100
    assert d["data"]["verdict"] in ("manageable", "some", "unsafe")
    assert not re.search(r"\b(is|it's|route is) (safe|clear)\b", d["reply"].lower())   # never certifies safety
    assert d["data"]["action"]["type"] == "set_destination"                             # the follow-up offer


async def test_sector_verdict_follows_the_15_degree_rule(aria):
    for direction in ("north", "south", "east", "west"):
        s = aria.sector(*BRADBURY, direction)
        if s["frac_over_15"] == 0 and s["frac_over_10"] < 0.05:
            assert s["verdict"] == "manageable"
        elif s["frac_over_15"] < 0.05:
            assert s["verdict"] == "some"
        else:
            assert s["verdict"] == "unsafe"


async def test_north_or_south_compares_both_directions(aria):
    d = ask(aria, "Should I go north or south?")
    opts = {o["direction"]: o for o in d["data"]["options"]}
    assert set(opts) == {"north", "south"}
    best = d["data"]["easier"]
    key = lambda o: (o["frac_over_15"], o["frac_over_10"], o["typical_deg"])
    assert key(opts[best]) <= key(opts["north" if best == "south" else "south"])


# ---------------------------------------------------------------------------
# Typos, short forms, multi-intent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q,topic", [
    ("wat is teh temprature at nite", "temperature"),
    ("hw cold does it get", "temperature"),
    ("is it dangerous to go eastt", "direction_safety"),
    ("dust stoorm risk?", "dust"),
    ("sunlihgt here?", "sunlight"),
    ("pls tell me abt radiation", "radiation"),
    ("cooold at night??", "temperature"),
])
async def test_typos_and_short_forms(aria, q, topic):
    assert ask(aria, q)["topic"] == topic, (q, normalize(q))


async def test_normalize_collapses_repeats_and_expands_short_forms():
    assert normalize("whats the TEMP at nite???") == "what is the temperature at night"
    assert normalize("is it soooo cold") == "is it so cold"


async def test_two_topics_in_one_question_get_one_paragraph_each_and_one_source_line(aria):
    d = ask(aria, "How cold is it and how much radiation is there?")
    assert d["topics"] == ["temperature", "radiation"]
    paras = d["reply"].split("\n\n")
    assert len(paras) == 3 and paras[-1].startswith("Source:")
    assert "PIA16913" in paras[-1] and "Hassler" in paras[-1]
    w = ask(aria, "what about wind and dust storms?")
    assert w["topics"] == ["wind", "dust"]


async def test_duplicate_topics_are_answered_once(aria):
    d = ask(aria, "does sun appear and is there sunlight in this region ever?")
    assert d["topics"] == ["sunlight"]


# ---------------------------------------------------------------------------
# Follow-ups (through the endpoint, with the history the frontend sends)
# ---------------------------------------------------------------------------
async def _chat(client, message, history):
    r = await client.post("/api/assistant/chat", json={
        "message": message, "history": history,
        "context": {"dataset_id": REAL_DS, "current_lon": BRADBURY[0], "current_lat": BRADBURY[1]}})
    assert r.status_code == 200, r.text
    d = r.json()
    history += [{"role": "user", "content": message}, {"role": "assistant", "content": d["reply"], "topic": d["topic"]}]
    return d


async def test_follow_ups_resolve_against_the_last_topic(client, aria):
    h: list[dict] = []
    assert (await _chat(client, "How cold does it get?", h))["data"]["mode"] == "general"
    night = await _chat(client, "and at night?", h)
    assert night["topic"] == "temperature" and night["data"]["mode"] == "night"
    danger = await _chat(client, "Would that be dangerous for me?", h)
    assert danger["topic"] == "survival"

    h = []
    assert (await _chat(client, "Is it safe to travel north?", h))["data"]["direction"] == "north"
    south = await _chat(client, "what about south?", h)
    assert south["topic"] == "direction_safety" and south["data"]["direction"] == "south"
    why = await _chat(client, "why?", h)
    assert why["topic"] == "direction_safety" and why["data"]["direction"] == "south"


async def test_unknown_question_is_warm_and_offers_suggestions(aria):
    for q in ("blorp", "tell me a joke", "qwerty asdf"):
        d = ask(aria, q)
        assert d["topic"] == "unknown"
        assert "didn't catch" not in d["reply"].lower()
        assert 3 <= len(d["suggestions"]) <= 4
        assert all(ask(aria, s)["topic"] != "unknown" for s in d["suggestions"])   # suggestions work


async def test_greeting(aria):
    d = ask(aria, "hi there")
    assert d["topic"] == "greeting" and d["suggestions"]


async def test_route_questions_without_and_with_a_route(aria):
    none = ask(aria, "Why is this route dangerous?")
    assert none["intent"] == "route_safety" and none["confidence"] == "none" and "Find Route" in none["reply"]
    route = {"mode": "terrain", "slope_max_deg": 12.3, "slope_mean_deg": 2.1, "cells_above_caution": 4,
             "caution_segments": 2, "caution_where": "end", "surface_length_3d_m": 2104.0,
             "planimetric_length_m": 2100.0, "elevation_gain_m": 31.0}
    d = ask(aria, "Why is this route dangerous?", route=route)
    assert "12.3°" in d["reply"] and "2.10 km" in d["reply"] and "near the end" in d["reply"]
    t = ask(aria, "How long is my route?", route=route)
    assert t["topic"] == "route_length" and "2.10 km" in t["reply"] and "walking-speed" in t["reply"]


# ---------------------------------------------------------------------------
# Every reply: answer first, "Source:" last, only numbers from app data / cited facts
# ---------------------------------------------------------------------------
BATTERY = (DAY_NIGHT + WIND + SUNLIGHT + NORTH + [
    "How cold is it?", "Will I freeze at night?", "Do I need thermal protection?", "How much radiation is there?",
    "what's the air pressure", "dust storm risk?", "Can astronauts survive outside?", "Am I safe here?",
    "Is this safe?", "Any hazards?", "What's the elevation?", "What's here?", "What's interesting near me?",
    "What minerals are nearby?", "Best path to clay?", "Where did Curiosity go?", "Where does your data come from?",
    "How far is Mount Sharp?", "Should I go north or south?", "Why is this route dangerous?", "hi", "blorp",
    "Temperature on this path?", "What's the weather and radiation like?", "is it safe to go west"])

_NUM = re.compile(r"(?<![A-Za-z])-?\d[\d,]*(?:\.\d+)?")


def _numbers(x, out: set[float]):
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        out.add(float(x))
    elif isinstance(x, str):
        for m in _NUM.finditer(x):
            out.add(float(m.group().replace(",", "")))
    elif isinstance(x, dict):
        for v in x.values():
            _numbers(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _numbers(v, out)


FACT_NUMBERS: set[float] = set()
_numbers([v for k, v in vars(wf).items() if not k.startswith("_")], FACT_NUMBERS)
_numbers([A.MAX_SLOPE_DEG, A.CAUTION_SLOPE_DEG, A.SECTOR_M, A.NEIGHBOURHOOD_M, A.HAZARD_RADIUS_M, A.MOLA_RES_M,
          5, 150], FACT_NUMBERS)   # 5 m grid, 150 km mineral search radius


def invented_numbers(d: dict, question: str) -> list[str]:
    """Numbers in the reply that match nothing in its data, the location, the cited facts or the question."""
    allowed = set(FACT_NUMBERS)
    _numbers([d["data"], d["location"], d.get("sources"), question], allowed)
    bad = []
    for m in _NUM.finditer(d["reply"]):
        tok = m.group().replace(",", "")
        n = abs(float(tok))
        dec = len(tok.split(".")[1]) if "." in tok else 0
        tol = 0.5 * 10 ** -dec + 1e-9
        if not any(abs(n - abs(c)) <= tol for v in allowed for c in (v, v / 1000, v * 100)):
            bad.append(m.group())
    return bad


async def test_number_checker_catches_an_invented_value(aria):
    d = ask(aria, "what about wind??")
    assert invented_numbers(d, "what about wind??") == []
    fake = {**d, "reply": "Winds are 37 km/h right now. " + d["reply"]}
    assert invented_numbers(fake, "what about wind??") == ["37"]


async def test_every_reply_ends_with_source_and_has_no_invented_numbers(aria):
    for q in BATTERY:
        d = ask(aria, q)
        lines = d["reply"].split("\n")
        assert lines[-1].startswith("Source: ") and len(lines[-1]) > len("Source: ") + 5, (q, lines[-1])
        assert not lines[0].startswith(("✅", "⚠️", "❌", "🔬", "📍", "📏", "❓")), q          # conversational
        assert invented_numbers(d, q) == [], (q, invented_numbers(d, q), d["reply"])
        assert "live" not in d["reply"].lower().replace("deliver", "") or "not live" in d["reply"].lower(), q
        assert "current" not in d["reply"].lower().replace("current location", ""), q


async def test_survival_answers_the_question_that_was_asked(aria):
    """'Would that be dangerous?' needs a yes; 'Can I survive outside?' needs a 'not without a suit'."""
    danger = ask(aria, "Would that be dangerous for me?", previous={"topic": "temperature", "message": "How cold at night?"})
    assert danger["topic"] == "survival" and danger["reply"].startswith("Yes")
    survive = ask(aria, "Can astronauts survive outside?")
    assert survive["topic"] == "survival" and survive["reply"].startswith(("No", "Not without"))
