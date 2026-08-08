OPS = {"eq", "ne", "gt", "lt", "present", "absent"}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def sieve_report(items: list[dict], rules: list[dict]) -> list[str]:
    seen = set()
    for rule in rules:
        name = rule.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("rule name must be a non-empty string")
        if name in seen:
            raise ValueError(f"rule name already used: {name}")
        seen.add(name)
        if rule.get("op") not in OPS:
            raise ValueError(f"unknown op: {rule.get('op')!r}")

    verdicts = []
    for item in items:
        verdict = "pass"
        for rule in rules:
            field = rule["field"]
            has = field in item
            value = item.get(field)
            op = rule["op"]
            if op == "present":
                ok = has
            elif op == "absent":
                ok = not has
            elif op == "eq":
                ok = has and value == rule["value"]
            elif op == "ne":
                ok = has and value != rule["value"]
            elif op == "gt":
                ok = has and _is_number(value) and value > rule["value"]
            else:
                ok = has and _is_number(value) and value < rule["value"]
            if not ok:
                verdict = rule["name"]
                break
        verdicts.append(verdict)
    return verdicts
