def audit_seating_chart(chart: list, glued: list, split: list) -> list:
    if not isinstance(chart, list) or not chart:
        raise ValueError("the chart is not a non-empty list")
    width = len(chart[0]) if isinstance(chart[0], list) else -1
    spot = {}
    for line, band in enumerate(chart):
        if not isinstance(band, list) or not band:
            raise ValueError("a band of the chart is not a non-empty list")
        if len(band) != width:
            raise ValueError("the bands of the chart are not all the same length")
        for cell, who in enumerate(band):
            if not isinstance(who, str):
                raise ValueError("a cell of the chart is not a string")
            if who == "":
                continue
            if who in spot:
                raise ValueError("a name is written on the chart twice")
            spot[who] = (line, cell)

    def read_pairs(raw):
        if not isinstance(raw, list):
            raise ValueError("a list of ties is not a list")
        ties = []
        for tie in raw:
            if not isinstance(tie, list) or len(tie) != 2:
                raise ValueError("a tie is not a list of two names")
            one, other = tie
            if not isinstance(one, str) or not isinstance(other, str):
                raise ValueError("a tie names something that is not a string")
            if one not in spot or other not in spot:
                raise ValueError("a tie names somebody the chart does not carry")
            if one == other:
                raise ValueError("a tie names one person twice")
            ties.append((one, other))
        return ties

    wanted = read_pairs(glued)
    banned = read_pairs(split)

    def touching(one, other):
        here = spot[one]
        there = spot[other]
        gap_down = abs(here[0] - there[0])
        gap_across = abs(here[1] - there[1])
        return (gap_down == 0 and gap_across == 1) or (
            gap_across == 0 and gap_down == 1
        )

    def label(one, other):
        return one + "-" + other if one < other else other + "-" + one

    faults = []
    for one, other in wanted:
        if not touching(one, other):
            faults.append("split:" + label(one, other))
    for one, other in banned:
        if touching(one, other):
            faults.append("touching:" + label(one, other))
    return faults
