def resolve_access(rules: list, request: dict) -> dict:
    for rule in rules:
        if rule["effect"] not in ("allow", "deny"):
            raise ValueError("bad effect: " + str(rule["effect"]))
        if rule["action"] == "":
            raise ValueError("empty action in rule")
    best = -1
    best_key = None
    for index, rule in enumerate(rules):
        segments = rule["path"]
        if len(segments) > len(request["path"]):
            continue
        if segments != request["path"][: len(segments)]:
            continue
        if rule["action"] != request["action"] and rule["action"] != "any":
            continue
        key = (
            len(segments),
            1 if rule["action"] != "any" else 0,
            1 if rule["effect"] == "deny" else 0,
            -index,
        )
        if best_key is None or key > best_key:
            best_key = key
            best = index
    if best == -1:
        return {"decision": "deny", "rule": -1}
    return {"decision": rules[best]["effect"], "rule": best}
