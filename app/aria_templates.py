"""ARIA's conversational wording (offline, no language model).

Every reply has the same shape:
    paragraph 1   a direct answer, then the reason (real numbers from app data or cited facts)
    paragraph 2   a practical tip and, optionally, a follow-up offer
    last line     "Source: …" naming exactly where the facts came from

Each slot has 2–3 wordings. The wording is picked from a hash of the (normalised) question, so
ARIA doesn't sound repetitive across questions but the same question always gets the same text.
Templates only arrange values passed in by app/assistant.py — they never contain measurements.
"""
from __future__ import annotations

import hashlib

T: dict[str, list[str]] = {
    # ---------------------------------------------------------------- temperature
    "temp.both.answer": ["At Gale Crater, nighttime is dramatically colder than daytime.",
                         "There's a huge difference between day and night at Gale Crater.",
                         "Nights at Gale Crater are far colder than the days."],
    "temp.both.reason": ["Historical measurements from Curiosity's REMS station show temperatures reaching around "
                         "{high} °C during the day and dropping to approximately {low} °C at night ({period}), a swing "
                         "of about {swing} °C.",
                         "Curiosity's REMS measurements show typical daytime highs of about {high} °C and night-time "
                         "lows of about {low} °C ({period}). That's a change of roughly {swing} °C every sol."],
    "temp.both.tip": ["That's a huge temperature difference, so astronauts would need reliable thermal protection, "
                      "especially after sunset.",
                      "Plan for reliable thermal protection, and avoid being outside after sunset without it."],
    "temp.night.answer": ["Nights at Gale Crater get extremely cold.", "It gets very cold here after sunset."],
    "temp.night.reason": ["Curiosity's REMS measurements show night-time lows of about {low} °C ({period}), compared "
                          "with daytime highs near {high} °C.",
                          "Historical REMS measurements show the air dropping to about {low} °C at night, against "
                          "roughly {high} °C at the warmest part of the day ({period})."],
    "temp.night.tip": ["Anyone outside at night would need strong thermal protection and heating.",
                       "Night work outside would need a well-heated suit, so plan outdoor tasks for daylight."],
    "temp.day.answer": ["Daytime is the mildest part of the sol here, but it's still cold.",
                        "Days at Gale Crater are much milder than the nights, though still cold by Earth standards."],
    "temp.day.reason": ["Curiosity's REMS measurements show typical daytime highs of about {high} °C ({period}), "
                        "while nights fell to about {low} °C.",
                        "Historical REMS data show the air reaching about {high} °C at the warmest part of the day "
                        "({period}), then dropping to about {low} °C at night."],
    "temp.day.tip": ["Daylight is the best window for outdoor work, but plan for the big drop after sunset.",
                     "Use the daytime for outdoor tasks and be back under thermal protection before sunset."],
    "temp.general.answer": ["It's very cold at Gale Crater, especially at night.",
                            "Gale Crater is cold, and the nights are much colder than the days."],
    "temp.general.reason": ["Curiosity's REMS measurements show typical daily highs of about {high} °C and lows of "
                            "about {low} °C ({period}).",
                            "Historical REMS measurements give typical highs of around {high} °C and lows of around "
                            "{low} °C ({period})."],
    "temp.general.tip": ["That swing of about {swing} °C means thermal protection matters, especially at night.",
                         "With a swing of roughly {swing} °C, plan for good thermal protection before sunset."],
    # ---------------------------------------------------------------- radiation
    "rad.answer": ["Radiation is a real concern on the surface here.",
                   "Yes, surface radiation is something to plan around at Gale Crater."],
    "rad.reason": ["Curiosity's RAD instrument measured about {dose} mSv per day at Gale ({src}).",
                   "On the surface, Curiosity's RAD instrument recorded a dose of about {dose} mSv per day ({src})."],
    "rad.tip": ["For longer stays, shielding and careful dose tracking matter.",
                "The longer the mission, the more shielding and dose tracking matter."],
    # ---------------------------------------------------------------- wind / pressure / dust
    "wind.answer": ["I don't have wind-speed readings available for your current location.",
                    "There are no wind measurements loaded in COSMIC TRAIL for this spot."],
    "wind.tip": ["If you're planning an outdoor route, I'd recommend checking updated weather observations before "
                 "heading out.",
                 "Before heading out, it's worth checking the latest weather observations from the mission team."],
    "pressure.answer": ["I don't have air-pressure readings loaded for this location.",
                        "COSMIC TRAIL has no pressure measurements for this spot."],
    "pressure.tip": ["Whatever the exact value, nobody can go outside here without a pressurised suit.",
                     "In practice that means a pressurised suit for every minute outside."],
    "dust.answer": ["I don't have dust or storm observations loaded for your location.",
                    "There are no dust-storm readings in COSMIC TRAIL for this spot."],
    "dust.tip": ["If a storm is reported, expect poor visibility and less solar power, and stay close to shelter.",
                 "Check the mission's weather updates before long walks; storms can cut visibility and solar power."],
    # ---------------------------------------------------------------- sunlight
    "sun.answer": ["Yes! Gale Crater experiences both daylight and nighttime as Mars rotates.",
                   "Yes, the Sun rises and sets here much as it does on Earth."],
    "sun.reason": ["A Martian day lasts about {h} hours and {m} minutes.",
                   "One Martian day, called a sol, lasts about {h} hours and {m} minutes."],
    "sun.tip": ["Sunlight is available here, although dust in the atmosphere can reduce visibility and solar energy "
                "production.",
                "So there's regular sunlight, but dust in the air can dim it and cut solar power."],
    # ---------------------------------------------------------------- survival
    # "Would that be dangerous?" needs a yes; "Can I survive outside?" needs a "not without".
    "survival.danger.answer": ["Yes, it would be very dangerous without a pressurised spacesuit.",
                               "Yes: without a spacesuit, exposure here would be deadly."],
    "survival.answer": ["Not without a pressurised spacesuit.",
                        "No, the surface would be deadly without a spacesuit."],
    "survival.reason": ["{air} Curiosity also measured night-time air temperatures of about {low} °C and a "
                        "radiation dose of about {dose} mSv per day.",
                        "{air} On top of that, nights fell to about {low} °C in Curiosity's measurements, and the "
                        "surface radiation dose was about {dose} mSv per day."],
    "survival.tip": ["Stay in a suit with thermal protection, and avoid long exposure, especially overnight.",
                     "A suit with heating and life support is essential, and overnight exposure is the hardest case."],
    # ---------------------------------------------------------------- direction safety
    "dir.manageable.answer": ["The terrain {dir} of your position looks manageable.",
                              "Heading {dir} looks fairly gentle."],
    "dir.some.answer": ["The terrain {dir} of your position looks relatively manageable, but there are some steeper "
                        "sections.",
                        "Heading {dir} is mostly manageable, though a few patches get steep."],
    "dir.unsafe.answer": ["I wouldn't head straight {dir} from here.",
                          "Going straight {dir} from here crosses ground that's too steep to walk."],
    "dir.reason": ["Within {radius} m to the {dir}, the slope is typically about {typical}° and reaches {max}°; "
                   "{pct_caution}% of the ground is steeper than 10° and {pct_max}% is over the 15° walking limit.",
                   "Looking {radius} m to the {dir}, the typical slope is about {typical}° with a maximum of {max}°. "
                   "{pct_caution}% of that ground is over 10°, and {pct_max}% is over the 15° limit."],
    "dir.manageable.tip": ["Still watch your footing: the 5 m map can't show small rocks or loose sand.",
                           "Keep an eye out for loose sand and rocks, which the 5 m map can't resolve."],
    "dir.some.tip": ["I'd recommend following the lower-slope path rather than a straight line.",
                     "A path that weaves around the steeper patches will be easier than a straight line."],
    "dir.unsafe.tip": ["It's better to go around: the route planner can find a path that stays under 15°.",
                       "Let the route planner find a way around that keeps every step under 15°."],
    "dir.offer": ["Would you like me to set a destination about {radius} m {dir} so the route planner can find the "
                  "safest path?",
                  "Want me to put a destination {radius} m {dir} of you, so you can calculate the safest route?"],
    "dir.compare.answer": ["{best} looks easier than {other}.", "I'd pick {best} over {other}."],
    "dir.compare.same": ["{best} and {other} look about the same.", "There's little to choose between {best} and {other}."],
    "dir.compare.reason": ["Within {radius} m, {best} is typically {b_typ}° (max {b_max}°, {b_pct}% over 10°), while "
                           "{other} is typically {o_typ}° (max {o_max}°, {o_pct}% over 10°)."],
    # ---------------------------------------------------------------- safety at a point
    "here.steep.answer": ["No, this exact spot is too steep to walk on.", "This spot is steeper than the walking limit."],
    "here.near.answer": ["This spot itself is walkable, but there's steep ground right next to you.",
                         "You're on walkable ground, but some ground close by is too steep."],
    "here.caution.answer": ["It's walkable here, though the ground around you is moderately steep.",
                            "This area is walkable, but parts of it are moderately steep."],
    "here.gentle.answer": ["This spot looks gentle and walkable.", "The ground here looks gentle."],
    "here.reason": ["The slope here is {here}°, and the steepest ground within {r} m reaches {max}° (the walking "
                    "limit is 15°).",
                    "Right here the slope is {here}°; within {r} m it gets up to {max}° (limit 15°)."],
    "here.tip": ["The 5 m map can't show boulders or loose sand, so still watch your footing.",
                 "Small rocks and soft sand don't show on the 5 m map, so take it carefully."],
    # ---------------------------------------------------------------- generic tails
    "unknown.answer": ["I'm not sure I understood that one, but I'd love to help.",
                       "Hmm, I didn't quite get that, so let me point you to what I can do."],
    "unknown.reason": ["I can tell you about slopes and safety around you or in any direction, temperatures, sunlight, "
                       "radiation, your planned route, minerals and science sites nearby.",
                       "I know the terrain around you, safe directions, temperatures, sunlight and radiation, your "
                       "route, minerals, science sites and where my data comes from."],
    "greeting.answer": ["Hi! I'm ARIA, your mission assistant for Gale Crater.",
                        "Hello! ARIA here, ready to help you plan your walk in Gale Crater."],
    "greeting.reason": ["I can check slopes and safety around you or in any direction, explain temperatures, "
                        "sunlight and radiation, review your planned route, and point out minerals and science sites.",
                        "Ask me whether a direction is safe, how cold it gets, how your route looks or what's "
                        "interesting nearby."],
}


def pick(seed: str, key: str) -> str:
    options = T[key]
    h = int(hashlib.md5(f"{seed}|{key}".encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def say(seed: str, key: str, **fields) -> str:
    return pick(seed, key).format(**fields)


def compose(answer: str, reason: str = "", tip: str = "", offer: str = "", source: str = "") -> str:
    """Direct answer + reason, then tip + offer, then the Source line."""
    first = " ".join(x.strip() for x in (answer, reason) if x and x.strip())
    second = " ".join(x.strip() for x in (tip, offer) if x and x.strip())
    paragraphs = [p for p in (first, second) if p]
    return "\n\n".join(paragraphs) + f"\n\nSource: {source or 'COSMIC TRAIL'}"
