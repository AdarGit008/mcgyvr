LEVELS = ["trace", "debug", "info", "warn", "error", "fatal"]


def route_log_records(rules: list, records: list, spare: str) -> list:
    if not isinstance(rules, list):
        raise ValueError("the rules must be a list")
    if not isinstance(records, list):
        raise ValueError("the records must be a list")
    if not isinstance(spare, str) or not spare:
        raise ValueError("the spare name must be a non-empty string")
    sinks = []
    floors = []
    tags = []
    halts = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("a rule must be a mapping")
        sink = rule.get("sink")
        least = rule.get("least")
        tag = rule.get("tag")
        stop = rule.get("stop")
        if not isinstance(sink, str) or not sink:
            raise ValueError("a sink must be a non-empty string")
        if not isinstance(least, str) or least not in LEVELS:
            raise ValueError("a level must be one of the six names")
        if not isinstance(tag, str):
            raise ValueError("a tag must be a string")
        if not isinstance(stop, bool):
            raise ValueError("stop is either true or false")
        sinks.append(sink)
        floors.append(LEVELS.index(least))
        tags.append(tag)
        halts.append(stop)
    routed = []
    for at, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("a record must be a mapping")
        level = record.get("level")
        tag = record.get("tag")
        if not isinstance(level, str) or level not in LEVELS:
            raise ValueError("a level must be one of the six names")
        if not isinstance(tag, str):
            raise ValueError("a tag must be a string")
        rank = LEVELS.index(level)
        taken = []
        held = set()
        for which, sink in enumerate(sinks):
            if rank < floors[which]:
                continue
            if tags[which] and tags[which] != tag:
                continue
            if sink not in held:
                held.add(sink)
                taken.append(sink)
            if halts[which]:
                break
        routed.append({"at": at, "sinks": taken if taken else [spare]})
    return routed
