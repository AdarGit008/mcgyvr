"""Wildcard label rules: compile once, then pick the most specific action."""


def segment_matches(segment, text, start):
    for offset, wanted in enumerate(segment):
        at = start + offset
        if wanted != "?" and (at >= len(text) or wanted != text[at]):
            return False
    return True


def compile_rules(pairs):
    rules = []
    seen = set()
    for pattern, action in pairs:
        if not isinstance(pattern, str) or pattern == "":
            raise ValueError("pattern must be a non-empty string")
        if not isinstance(action, str) or action == "":
            raise ValueError("action must be a non-empty string")
        if pattern.count("*") > 1:
            raise ValueError("at most one * per pattern")
        if pattern in seen:
            raise ValueError("pattern repeated: " + pattern)
        seen.add(pattern)
        literals = sum(1 for piece in pattern if piece not in "?*")
        rules.append({"pattern": pattern, "action": action, "literals": literals})
    return rules


def rule_fits(pattern, text):
    star = pattern.find("*")
    if star == -1:
        return len(pattern) == len(text) and segment_matches(pattern, text, 0)
    head = pattern[:star]
    tail = pattern[star + 1:]
    if len(text) < len(head) + len(tail):
        return False
    return segment_matches(head, text, 0) and segment_matches(
        tail, text, len(text) - len(tail)
    )


def best_action(rules, text):
    if not isinstance(text, str):
        raise ValueError("candidate must be a string")
    best = None
    for rule in rules:
        if not rule_fits(rule["pattern"], text):
            continue
        if best is None or rule["literals"] > best["literals"]:
            best = rule
    return None if best is None else best["action"]
