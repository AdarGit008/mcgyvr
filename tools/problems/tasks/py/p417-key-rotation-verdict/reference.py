import re


def _whole(value, floor):
    return isinstance(value, int) and not isinstance(value, bool) and value >= floor


def _read_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("an entry must be a record")
    if "digest" not in entry or "step" not in entry:
        raise ValueError("an entry needs both digest and step")
    digest = entry["digest"]
    if not isinstance(digest, str) or re.fullmatch(r"[a-z0-9]+", digest) is None:
        raise ValueError("a digest is small letters and digits only")
    if not _whole(entry["step"], 0):
        raise ValueError("a step must be a whole number of zero or more")
    return {"digest": digest, "step": entry["step"]}


def judge_key_rotation(ledger: list, offer: dict, rules: dict) -> dict:
    if not isinstance(ledger, list):
        raise ValueError("the ledger must be a list")
    past = [_read_entry(entry) for entry in ledger]
    for older, newer in zip(past, past[1:]):
        if newer["step"] <= older["step"]:
            raise ValueError("the ledger steps must rise strictly")
    put = _read_entry(offer)
    if past and put["step"] <= past[-1]["step"]:
        raise ValueError("the offer must sit above the newest ledger step")
    if not isinstance(rules, dict):
        raise ValueError("rules must be a record")
    for key in ("keep", "gap", "span", "runs", "window"):
        if key not in rules:
            raise ValueError("rules is missing " + key)
    for key in ("keep", "gap"):
        if not _whole(rules[key], 0):
            raise ValueError(key + " must be a whole number of zero or more")
    for key in ("span", "runs", "window"):
        if not _whole(rules[key], 1):
            raise ValueError(key + " must be a whole number of one or more")
    if rules["gap"] > rules["span"]:
        raise ValueError("gap may not be larger than span")

    broken = []
    recent = [] if rules["keep"] == 0 else past[max(0, len(past) - rules["keep"]) :]
    if any(entry["digest"] == put["digest"] for entry in recent):
        broken.append("reused")
    if past:
        since = put["step"] - past[-1]["step"]
        if since < rules["gap"]:
            broken.append("toosoon")
        if since > rules["span"]:
            broken.append("stale")
    floor = put["step"] - rules["window"]
    busy = len([entry for entry in past if entry["step"] > floor])
    if busy >= rules["runs"]:
        broken.append("churn")
    return {"verdict": "accept" if not broken else "refuse", "broken": broken}
