def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def quote_freight_run(bands: list, kilos: int) -> dict:
    if not isinstance(bands, list) or not bands:
        raise ValueError("the bands must be a non-empty list")
    starts = []
    rates = []
    for band in bands:
        if not isinstance(band, dict):
            raise ValueError("a band must be a mapping")
        start = band.get("from")
        rate = band.get("perKilo")
        if not _whole(start) or start < 0:
            raise ValueError("a starting weight must be a whole number of nought or more")
        if not _whole(rate) or rate < 0:
            raise ValueError("a rate must be a non-negative whole number")
        if not starts:
            if start != 0:
                raise ValueError("the first band must start at nought")
        elif start <= starts[-1]:
            raise ValueError("the starting weights must climb strictly")
        starts.append(start)
        rates.append(rate)
    if not _whole(kilos) or kilos < 1:
        raise ValueError("the consignment weight must be a whole number of one or more")
    split = []
    cents = 0
    for at, start in enumerate(starts):
        stop = starts[at + 1] if at + 1 < len(starts) else kilos
        covered = max(0, min(stop, kilos) - start)
        charge = covered * rates[at]
        split.append(charge)
        cents += charge
    return {"split": split, "cents": cents}
