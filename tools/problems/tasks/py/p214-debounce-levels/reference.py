def debounce_levels(samples: object, hold: object) -> list:
    if not isinstance(samples, list) or not samples:
        raise ValueError("the sample list must be a non-empty list")
    for sample in samples:
        if isinstance(sample, bool) or not isinstance(sample, int):
            raise ValueError("a sample must be 0 or 1")
        if sample not in (0, 1):
            raise ValueError("a sample must be 0 or 1")
    if isinstance(hold, bool) or not isinstance(hold, int) or hold < 1:
        raise ValueError("hold must be a positive whole number")
    settled = samples[0]
    tally = 0
    report = [settled]
    for sample in samples[1:]:
        if sample == settled:
            tally = 0
        else:
            tally += 1
            if tally >= hold:
                settled = sample
                tally = 0
        report.append(settled)
    return report
