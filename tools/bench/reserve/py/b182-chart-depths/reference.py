def chart_depths(chart):
    """Rung of every member of a crew chart, counting the chief as zero."""
    rungs = {}
    for member in chart:
        climbed = []
        climbing = set()
        at = member
        while at != "" and at not in rungs:
            if at in climbing:
                raise ValueError("the chart circles back at " + at)
            if at not in chart:
                raise ValueError("the chart does not list " + at)
            climbing.add(at)
            climbed.append(at)
            at = chart[at]
        rung = -1 if at == "" else rungs[at]
        for name in reversed(climbed):
            rung += 1
            rungs[name] = rung
    return rungs
