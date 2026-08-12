"""Normalize a locale tag to canonical separators and letter case."""

import re


def _title_case(segment):
    return segment[0].upper() + segment[1:].lower()


def normalize_locale_tag(tag: str) -> str:
    if not isinstance(tag, str):
        raise ValueError("normalize_locale_tag expects a string")
    if tag == "":
        raise ValueError("empty locale tag")
    segments = re.split(r"[-_]", tag)
    if any(segment == "" for segment in segments):
        raise ValueError("empty subtag")
    core = segments
    private_use = None
    for position, segment in enumerate(segments):
        if segment.lower() == "x":
            core = segments[:position]
            private_use = segments[position + 1 :]
            break
    if not core:
        raise ValueError("missing language subtag")
    if len(core) > 4:
        raise ValueError("too many subtags before the private-use part")
    if re.fullmatch(r"[A-Za-z]{2,3}", core[0]) is None:
        raise ValueError("language subtag must be 2 or 3 letters")
    normalized = [core[0].lower()]
    index = 1
    if index < len(core) and re.fullmatch(r"[A-Za-z]{4}", core[index]):
        normalized.append(_title_case(core[index]))
        index += 1
    if index < len(core) and re.fullmatch(r"[A-Za-z]{2}|[0-9]{3}", core[index]):
        normalized.append(core[index].upper())
        index += 1
    if index < len(core) and re.fullmatch(r"[A-Za-z0-9]{5,8}", core[index]):
        normalized.append(core[index].lower())
        index += 1
    if index < len(core):
        raise ValueError("subtag fits no slot in order")
    if private_use is not None:
        if not private_use:
            raise ValueError("x marker with nothing after it")
        normalized.append("x")
        for segment in private_use:
            if re.fullmatch(r"[A-Za-z0-9]{1,8}", segment) is None:
                raise ValueError("bad private-use subtag")
            normalized.append(segment.lower())
    return "-".join(normalized)
