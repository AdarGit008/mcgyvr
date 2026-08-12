"""Clock-time helpers and the leg-by-leg arrival tracker built on them."""

import re


def parse_clock(text):
    if not isinstance(text, str) or re.fullmatch(r"\d\d:\d\d", text) is None:
        raise ValueError("a clock reads HH:MM")
    hours, minutes = int(text[:2]), int(text[3:])
    if hours > 23 or minutes > 59:
        raise ValueError("no such clock time")
    return hours * 60 + minutes


def format_clock(minutes):
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise ValueError("minutes must lie in 0..1439")
    if minutes < 0 or minutes > 1439:
        raise ValueError("minutes must lie in 0..1439")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def leg_arrivals(departure, legs):
    start = parse_clock(departure)
    arrivals = []
    elapsed = 0
    for leg in legs:
        if not isinstance(leg, list) or len(leg) != 2:
            raise ValueError("a leg is [travel, layover]")
        travel, layover = leg
        for value in (travel, layover):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("leg minutes must be integers")
        if travel <= 0:
            raise ValueError("travel minutes must be a positive integer")
        if layover < 0:
            raise ValueError("layover minutes must be a non-negative integer")
        elapsed += travel
        absolute = start + elapsed
        arrivals.append([format_clock(absolute % 1440), absolute // 1440])
        elapsed += layover
    return arrivals
