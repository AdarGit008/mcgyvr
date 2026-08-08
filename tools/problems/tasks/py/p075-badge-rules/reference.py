def evaluate_rules(rules: list, request: dict) -> str:
    for rule in rules:
        role_ok = rule["role"] == request["role"] or rule["role"] == "everyone"
        door_ok = rule["door"] == request["door"] or rule["door"] == "all"
        if role_ok and door_ok:
            return rule["effect"]
    return "deny"
