def bin_tallies(readings, edges):
    if len(edges) < 2:
        raise ValueError("need at least two edges")
    for left, right in zip(edges, edges[1:]):
        if right <= left:
            raise ValueError("edges must be strictly increasing")
    bands = [0] * (len(edges) - 1)
    below = 0
    above = 0
    for reading in readings:
        if reading < edges[0]:
            below += 1
        elif reading >= edges[-1]:
            above += 1
        else:
            for i in range(len(bands)):
                if reading < edges[i + 1]:
                    bands[i] += 1
                    break
    return {"bands": bands, "below": below, "above": above}
