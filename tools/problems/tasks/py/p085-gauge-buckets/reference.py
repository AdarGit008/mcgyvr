def gauge_buckets(pulses, base, width, pockets):
    tallies = [0] * (pockets + 2)
    top = base + width * pockets
    for pulse in pulses:
        if pulse < base:
            tallies[0] += 1
        elif pulse >= top:
            tallies[pockets + 1] += 1
        else:
            tallies[1 + (pulse - base) // width] += 1
    return tallies
