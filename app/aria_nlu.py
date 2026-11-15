"""ARIA's question understanding — offline, no language model, standard library only.

1. normalize()  lowercase, drop punctuation, collapse repeated letters ("cooold" → "cold"),
                expand short forms ("temp", "wat", "hw", "u", "pls") and fix typos with
                difflib against ARIA's own vocabulary.
2. understand() topics (several per question: "does the sun appear and is there sunlight?"),
                modifiers (day/night, comparison, compass directions, "why", safety,
                distance/time) and named places.
3. resolve()    picks the intent(s) to answer, using the previous topic for follow-ups such as
                "and at night?", "why?" or "what about south?".
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- normalisation
SHORT_FORMS = {
    "temp": "temperature", "temps": "temperature", "tempreture": "temperature", "temprature": "temperature",
    "wat": "what", "wht": "what", "wut": "what", "whats": "what is", "wheres": "where is", "hows": "how is",
    "hw": "how", "u": "you", "ur": "your", "r": "are", "pls": "please", "plz": "please", "thx": "thanks",
    "abt": "about", "nite": "night", "tonite": "tonight", "shud": "should", "shld": "should", "cn": "can",
    "im": "i am", "dont": "do not", "cant": "cannot", "isnt": "is not", "thru": "through", "wx": "weather",
    "rad": "radiation", "km": "km", "mins": "minutes", "hrs": "hours", "n": "and", "b4": "before",
}

# Topic → trigger words / phrases (normalised form). Order matters only for ties.
TOPICS: dict[str, tuple[str, ...]] = {
    "greeting": ("hi", "hello", "hey", "hiya", "salam", "assalam", "greetings", "good morning", "good evening",
                 "help", "what can you do", "who are you", "how does this work", "thanks", "thank you"),
    "temperature": ("temperature", "cold", "colder", "coldest", "hot", "hotter", "warm", "warmer", "freeze",
                    "freezing", "frozen", "heat", "degrees", "celsius", "chilly", "frost", "thermal"),
    "radiation": ("radiation", "radioactive", "dose", "msv", "sievert", "cosmic rays"),
    "wind": ("wind", "winds", "windy", "gust", "gusts", "breeze"),
    "pressure": ("pressure", "air pressure", "atmospheric pressure", "barometric", "atmosphere", "air"),
    "dust": ("dust", "dusty", "dust storm", "dust storms", "storm", "storms", "sandstorm"),
    "sunlight": ("sun", "sunlight", "sunny", "sunshine", "daylight", "sunrise", "sunset", "solar", "sol",
                 "day length", "how long is a day", "length of a day", "light", "dark", "darkness", "shine"),
    "survival": ("survive", "survival", "spacesuit", "suit", "breathe", "breathing", "oxygen", "alive",
                 "overnight", "exposed", "exposure", "helmet", "die", "protection", "protect"),
    "weather": ("weather", "climate", "forecast", "conditions"),
    "safety": ("safe", "safely", "safety", "dangerous", "danger", "risky", "risk", "unsafe"),
    "hazard": ("hazard", "hazards", "obstacle", "obstacles", "cliff", "cliffs"),
    "steep": ("steep", "steepness", "slope", "slopes", "gradient", "incline", "climb"),
    "route": ("route", "path", "traverse", "trip", "journey", "my way"),
    "length": ("how far", "far", "distance", "how long", "length", "time", "hours", "minutes", "take"),
    "elevation": ("elevation", "height", "altitude", "how high", "how low", "deep", "sea level"),
    "place": ("here", "this place", "this spot", "this area", "this location", "where am i", "my location",
              "current location", "what is here", "around me", "nearby"),
    "interesting": ("interesting", "cool", "special", "notable", "science", "scientific", "explore", "visit",
                    "worth seeing", "sites", "site"),
    "minerals": ("mineral", "minerals", "clay", "clays", "rock", "rocks", "sulfate", "sulphate", "hematite",
                 "smectite", "crism", "mudstone", "carbonate", "silica", "geology", "geologic"),
    "curiosity": ("curiosity", "rover", "msl", "curiosity route", "curiosity path", "waypoint", "waypoints"),
    "data": ("data", "source", "sources", "hirise", "dataset", "dtm", "accurate", "accuracy", "resolution",
             "usgs", "mola", "satellite"),
}
DAY_WORDS = ("day", "daytime", "noon", "afternoon", "morning", "daylight hours")
NIGHT_WORDS = ("night", "nighttime", "tonight", "evening", "after sunset", "nights")
COMPARE_WORDS = ("compared", "compare", "comparison", "versus", "vs", "difference", "different", "differ",
                 "between", "than", "swing", "range", "change")
WHY_WORDS = ("why", "how come", "reason", "explain")
MOVE_WORDS = ("go", "travel", "walk", "head", "move", "drive", "hike", "trek", "going", "heading", "walking",
              "travelling", "traveling", "explore")
DIRECTION_WORDS = {
    "northeast": "northeast", "north east": "northeast", "northwest": "northwest", "north west": "northwest",
    "southeast": "southeast", "south east": "southeast", "southwest": "southwest", "south west": "southwest",
    "north": "north", "south": "south", "east": "east", "west": "west",
}
BEARINGS = {"north": 0.0, "northeast": 45.0, "east": 90.0, "southeast": 135.0, "south": 180.0,
            "southwest": 225.0, "west": 270.0, "northwest": 315.0}

_VOCAB = sorted({w for words in TOPICS.values() for p in words for w in p.split()}
                | {w for p in DAY_WORDS + NIGHT_WORDS + COMPARE_WORDS + WHY_WORDS + MOVE_WORDS for w in p.split()}
                | {w for p in DIRECTION_WORDS for w in p.split()})
# Common English words that must never be "corrected" into a topic word.
_STOP = {"what", "where", "when", "which", "who", "how", "the", "and", "are", "is", "it", "this", "that", "there",
         "about", "with", "from", "into", "your", "you", "can", "could", "would", "should", "will", "does", "did",
         "have", "has", "had", "get", "got", "need", "want", "like", "much", "many", "very", "some", "any", "ever",
         "here", "near", "next", "over", "under", "then", "than", "also", "just", "only", "still", "really",
         "please", "thanks", "tell", "show", "give", "know", "mars", "gale", "crater", "region", "area", "place"}


def normalize(text: str) -> str:
    t = text.lower().replace("’", "'").replace("'", "")
    t = re.sub(r"[^a-z0-9°.\- ]+", " ", t)
    t = re.sub(r"(?<![0-9])[.\-](?![0-9])", " ", t)
    t = re.sub(r"([a-z])\1{2,}", r"\1", t)               # "cooold" → "cold", "pleeease" → "please"
    out = []
    for w in t.split():
        w = SHORT_FORMS.get(w, w)
        if w not in _VOCAB and w not in _STOP and len(w) >= 4 and not w.isdigit():
            fix = difflib.get_close_matches(w, _VOCAB, n=1, cutoff=0.84)
            if fix:
                w = fix[0]
        out.append(w)
    return " ".join(out)


def _has(text: str, phrases) -> bool:
    return any(re.search(rf"\b{re.escape(p)}\b", text) for p in phrases)


# ---------------------------------------------------------------- understanding
@dataclass
class Parse:
    text: str                                   # normalised question
    topics: list[str] = field(default_factory=list)
    time: str | None = None                     # "day" | "night" | "both"
    compare: bool = False
    why: bool = False
    move: bool = False
    directions: list[str] = field(default_factory=list)


def understand(message: str) -> Parse:
    t = normalize(message)
    p = Parse(t)
    p.topics = [k for k, words in TOPICS.items() if _has(t, words)]
    day, night = _has(t, DAY_WORDS), _has(t, NIGHT_WORDS)
    p.time = "both" if day and night else ("day" if day else ("night" if night else None))
    p.compare = _has(t, COMPARE_WORDS) or p.time == "both"
    p.why = _has(t, WHY_WORDS)
    p.move = _has(t, MOVE_WORDS)
    found = []
    for phrase, d in sorted(DIRECTION_WORDS.items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(rf"\b{phrase}\b", t):
            if not any(a <= m.start() < b for _, a, b in found):
                found.append((d, m.start(), m.end()))
    for d, _, _ in sorted(found, key=lambda f: f[1]):
        if d not in p.directions:
            p.directions.append(d)
    # "sun" + "sunlight" and similar overlaps are one topic; "light"/"dark" alone only with no other topic.
    if "sunlight" in p.topics and not _has(t, ("sun", "sunlight", "sunny", "sunshine", "daylight", "sunrise",
                                                "sunset", "solar", "sol", "day length", "how long is a day",
                                                "length of a day")) and len(p.topics) > 1:
        p.topics.remove("sunlight")
    if "pressure" in p.topics and not _has(t, ("pressure", "barometric", "atmosphere")) and (
            "survival" in p.topics or len(p.topics) > 1):
        p.topics.remove("pressure")            # "air" alone ("can I breathe the air?") → survival
    return p


# Intents ARIA can answer. ENVIRONMENT intents can be combined in one reply.
ENVIRONMENT = ("temperature", "radiation", "wind", "pressure", "dust", "sunlight", "survival")


@dataclass
class Resolved:
    intents: list[str]
    parse: Parse
    follow_up: bool = False


def resolve(message: str, previous: dict | None = None) -> Resolved:
    """Pick what to answer. `previous`: {"topic": ..., "directions": [...]} of ARIA's last answer."""
    p = understand(message)
    t, topics = p.text, set(p.topics)
    prev = (previous or {}).get("topic")

    def out(*intents, follow=False):
        return Resolved(list(intents), p, follow)

    # Route questions about the planned route (not the map point).
    if "route" in topics and (topics & {"safety", "hazard", "steep"} or p.why):
        return out("route_danger")
    if "route" in topics and "length" in topics:
        return out("route_length")
    if "route" in topics and "temperature" in topics:
        return out("route_thermal")
    if "route" in topics and not (topics - {"route", "place"}):
        return out("route_danger")                 # "Analyze my route", "how does my route look?"
    # Compass directions: "Is it safe to travel north?", "north or south?", "what about south?".
    if p.directions and (p.move or topics & {"safety", "steep", "hazard"} or len(p.directions) > 1
                         or prev == "direction_safety" or not topics):
        return out("direction_safety", follow=prev == "direction_safety" and not (p.move or topics))
    # Environment: one or several topics in one question.
    env = [i for i in ENVIRONMENT if i in topics]
    if "weather" in topics:
        if not env:
            env = ["temperature", "radiation"]
        elif "temperature" not in env:
            env.insert(0, "temperature")
    if "temperature" not in env and p.time and topics <= {"place", "safety", "greeting"} and not p.directions \
            and prev in ("temperature", "survival", "sunlight", None):
        if prev in ("temperature", "survival") or "safety" not in topics:
            env.insert(0, "temperature")
    if env:
        # "Will I freeze / survive?" questions are about exposure; keep temperature too if asked explicitly.
        if "survival" in env and "temperature" in env and not _has(t, ("temperature", "degrees", "celsius")):
            env.remove("temperature")
        return out(*env)
    # Follow-ups that only make sense with the previous topic.
    if prev and (p.why or _has(t, ("what about", "how about", "and", "would that", "is that", "does that"))
                 and not (topics - {"safety", "place"})):
        if "safety" in topics and prev in ("temperature", "radiation", "wind", "dust", "pressure", "sunlight"):
            return out("survival", follow=True)
        if prev in ENVIRONMENT or prev in ("safety_here", "direction_safety", "hazard", "route_danger", "place_info", "minerals",
                                           "elevation", "science_sites", "curiosity_route", "data_sources"):
            return out(prev, follow=True)
    if "hazard" in topics:
        return out("hazard")
    if topics & {"safety", "steep"}:
        return out("safety_here")
    if "curiosity" in topics:
        return out("curiosity_route")
    if "data" in topics:
        return out("data_sources")
    if "minerals" in topics:
        return out("minerals")
    if "elevation" in topics:
        return out("elevation")
    if "length" in topics:
        return out("distance")
    if "interesting" in topics:
        return out("science_sites")
    if "place" in topics:
        return out("place_info")
    if "greeting" in topics:
        return out("greeting")
    return out("unknown")
