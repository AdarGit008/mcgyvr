def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _in_range(value):
    return abs(value) <= 1000000


def _settle(num, den):
    if num >= 0:
        return (2 * num + den) // (2 * den)
    return -((2 * -num + den) // (2 * den))


def sweep_probe_scales(channels: list, samples: list) -> dict:
    if not isinstance(channels, list):
        raise ValueError("sweep_probe_scales expects a list of channels")
    decks = {}
    order = []
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError("a channel is not a record")
        if sorted(channel) != ["bias", "channel", "ladder"]:
            raise ValueError("a channel's keys are not exactly the three named")
        name = channel["channel"]
        if not isinstance(name, str) or not name:
            raise ValueError("a channel name is not a non-empty string")
        if name in decks:
            raise ValueError("two channels answer to one name")
        ladder = channel["ladder"]
        if not isinstance(ladder, list) or len(ladder) < 2:
            raise ValueError("a ladder is not a list of at least two rungs")
        for rung in ladder:
            if not isinstance(rung, list) or len(rung) != 2:
                raise ValueError("a rung is not a list of exactly two entries")
            for entry in rung:
                if not _whole(entry):
                    raise ValueError("a rung entry is not a whole number")
                if not _in_range(entry):
                    raise ValueError("a rung entry reaches beyond a million away from nought")
        for lower, upper in zip(ladder, ladder[1:]):
            if upper[0] <= lower[0]:
                raise ValueError("the tick figures do not rise strictly from rung to rung")
        bias = channel["bias"]
        if not _whole(bias):
            raise ValueError("a bias is not a whole number")
        if not _in_range(bias):
            raise ValueError("a bias reaches beyond a million away from nought")
        decks[name] = (ladder, bias)
        order.append(name)

    if not isinstance(samples, list):
        raise ValueError("sweep_probe_scales expects a list of samples")
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("a sample is not a record")
        if sorted(sample) != ["channel", "count"]:
            raise ValueError("a sample's keys are not exactly the two named")
        if not isinstance(sample["channel"], str) or sample["channel"] not in decks:
            raise ValueError("a sample names no declared channel")
        if not _whole(sample["count"]):
            raise ValueError("a count is not a whole number")
        if not _in_range(sample["count"]):
            raise ValueError("a count reaches beyond a million away from nought")

    readings = []
    seen = {}
    low = 0
    high = 0

    for sample in samples:
        name = sample["channel"]
        count = sample["count"]
        ladder, bias = decks[name]
        first = ladder[0]
        last = ladder[-1]

        num = 0
        den = 1
        if count <= first[0]:
            num = first[1]
            if count < first[0]:
                low += 1
        elif count >= last[0]:
            num = last[1]
            if count > last[0]:
                high += 1
        else:
            index = 0
            while ladder[index + 1][0] <= count:
                index += 1
            lo = ladder[index]
            hi = ladder[index + 1]
            den = hi[0] - lo[0]
            num = lo[1] * den + (count - lo[0]) * (hi[1] - lo[1])

        value = _settle(num + bias * den, den)
        readings.append(f"{name} {value}")
        if name in seen:
            held = seen[name]
            seen[name] = (min(held[0], value), max(held[1], value))
        else:
            seen[name] = (value, value)

    span = [f"{name} {seen[name][0]} {seen[name][1]}" for name in order if name in seen]
    return {"readings": readings, "low": low, "high": high, "span": span}
