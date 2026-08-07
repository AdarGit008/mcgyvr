import re

SPAN = re.compile(r"(0|[1-9]\d*)?\.\.(0|[1-9]\d*)?((?:!(?:0|[1-9]\d*))*)")


def intersect_build_spans(spans: list[str]) -> str:
    if not isinstance(spans, list) or not spans:
        raise ValueError("at least one span is required")
    lo = None
    hi = None
    strikes = set()
    for span in spans:
        if not isinstance(span, str):
            raise ValueError("span must be a string")
        m = SPAN.fullmatch(span)
        if m is None:
            raise ValueError(f"malformed span: {span}")
        span_lo = None if m.group(1) is None else int(m.group(1))
        span_hi = None if m.group(2) is None else int(m.group(2))
        if span_lo is not None and span_hi is not None and span_lo > span_hi:
            raise ValueError(f"reversed limits: {span}")
        marks = [int(n) for n in m.group(3)[1:].split("!")] if m.group(3) else []
        for struck in marks:
            if (span_lo is not None and struck < span_lo) or (
                span_hi is not None and struck > span_hi
            ):
                raise ValueError(f"strike outside its span: {span}")
            strikes.add(struck)
        if span_lo is not None:
            lo = span_lo if lo is None else max(lo, span_lo)
        if span_hi is not None:
            hi = span_hi if hi is None else min(hi, span_hi)
    survivors = {
        struck
        for struck in strikes
        if (lo is None or struck >= lo) and (hi is None or struck <= hi)
    }
    while lo is not None and lo in survivors:
        survivors.discard(lo)
        lo += 1
    while hi is not None and hi in survivors:
        survivors.discard(hi)
        hi -= 1
    if lo is not None and hi is not None and lo > hi:
        return "empty"
    tail = "".join(f"!{struck}" for struck in sorted(survivors))
    left = "" if lo is None else str(lo)
    right = "" if hi is None else str(hi)
    return f"{left}..{right}{tail}"
