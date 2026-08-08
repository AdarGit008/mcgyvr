KINDS = ("full", "diff", "incr")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def plan_restore_chain(runs: list, target: int) -> dict:
    if not isinstance(runs, list) or not runs:
        raise ValueError("runs must be a non-empty list")
    table = {}
    labels = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("each run is a record")
        for key in ("label", "kind", "step", "sound"):
            if key not in run:
                raise ValueError("a run is missing " + key)
        label = run["label"]
        if not isinstance(label, str) or label == "":
            raise ValueError("label must be a non-empty string")
        if label in labels:
            raise ValueError("two runs share a label")
        labels.add(label)
        if run["kind"] not in KINDS:
            raise ValueError("kind must be full, diff or incr")
        if not _whole(run["step"]):
            raise ValueError("step must be a whole number of zero or more")
        if run["step"] in table:
            raise ValueError("two runs share a step")
        if not isinstance(run["sound"], bool):
            raise ValueError("sound must be a boolean")
        table[run["step"]] = run
    if not _whole(target):
        raise ValueError("target must be a whole number of zero or more")
    if target not in table:
        raise ValueError("no run carries the target step")
    order = sorted(table)
    chain = []
    step = target
    while True:
        run = table[step]
        if not run["sound"]:
            return {"ok": "no", "chain": [], "reason": "damaged"}
        chain.append(run["label"])
        if run["kind"] == "full":
            chain.reverse()
            return {"ok": "yes", "chain": chain, "reason": ""}
        earlier = [s for s in order if s < step]
        if not earlier:
            return {"ok": "no", "chain": [], "reason": "nofull"}
        if run["kind"] == "incr":
            step = earlier[-1]
            continue
        fulls = [
            s for s in earlier if table[s]["kind"] == "full" and table[s]["sound"]
        ]
        if not fulls:
            return {"ok": "no", "chain": [], "reason": "nofull"}
        step = fulls[-1]
