"""How a run of calls fared against a protective latch."""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def summarise_latch_run(run: list, dial: dict) -> dict:
    if not isinstance(run, list):
        raise ValueError("the run must be a list")
    for word in run:
        if word not in ("good", "bad"):
            raise ValueError("a word is either good or bad")
    if not isinstance(dial, dict):
        raise ValueError("the dial must be a record")
    for key in ("span", "sour", "wait", "trials"):
        if key not in dial:
            raise ValueError("the dial is missing " + key)
        if not _whole(dial[key]):
            raise ValueError(key + " must be a whole number of one or more")
    if dial["sour"] > dial["span"]:
        raise ValueError("sour may not be larger than span")
    mode = "shut"
    countdown = 0
    wins = 0
    tried = 0
    shed = 0
    trips = 0
    ledger = []
    for word in run:
        if mode == "shut":
            tried += 1
            ledger.append(word)
            while len(ledger) > dial["span"]:
                ledger.pop(0)
            if len(ledger) == dial["span"] and ledger.count("bad") >= dial["sour"]:
                mode = "tripped"
                countdown = dial["wait"]
                trips += 1
                ledger = []
        elif mode == "tripped":
            shed += 1
            countdown -= 1
            if countdown == 0:
                mode = "testing"
                wins = 0
        else:
            tried += 1
            if word == "good":
                wins += 1
                if wins == dial["trials"]:
                    mode = "shut"
                    ledger = []
            else:
                mode = "tripped"
                countdown = dial["wait"]
                trips += 1
                ledger = []
    return {"mode": mode, "tried": tried, "shed": shed, "trips": trips}
