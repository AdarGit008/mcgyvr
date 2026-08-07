import re


def _group_options(body):
    if ".." in body:
        m = re.fullmatch(r"(\d+)\.\.(\d+)", body)
        if m is None:
            raise ValueError("malformed span")
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            raise ValueError("span out of order")
        if hi - lo + 1 > 500:
            raise ValueError("too many combinations")
        width = len(m.group(1))
        return [str(v).zfill(width) for v in range(lo, hi + 1)]
    options = body.split("|")
    for option in options:
        if re.fullmatch(r"[A-Za-z0-9]+", option) is None:
            raise ValueError("bad alternation choice")
    return options


def expand_span_grammar(pattern: str) -> list:
    if not isinstance(pattern, str):
        raise ValueError("pattern must be a string")
    parts = []
    literal = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "~":
            nxt = pattern[i + 1] if i + 1 < len(pattern) else None
            if nxt is None or nxt not in "<>|~":
                raise ValueError("bad escape")
            literal += nxt
            i += 2
        elif ch == ">":
            raise ValueError("stray group close")
        elif ch == "<":
            end = pattern.find(">", i + 1)
            if end == -1:
                raise ValueError("unclosed group")
            body = pattern[i + 1 : end]
            if "<" in body or "~" in body:
                raise ValueError("forbidden character in group")
            if literal:
                parts.append([literal])
                literal = ""
            parts.append(_group_options(body))
            i = end + 1
        else:
            literal += ch
            i += 1
    if literal:
        parts.append([literal])
    count = 1
    for options in parts:
        count *= len(options)
        if count > 500:
            raise ValueError("too many combinations")
    results = [""]
    for options in parts:
        results = [stem + option for stem in results for option in options]
    return sorted(set(results))
