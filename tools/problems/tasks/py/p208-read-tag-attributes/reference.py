import re

STEM = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
NAME = re.compile(r"[a-z][a-z0-9-]*")
STEM_CHARS = re.compile(r"[A-Za-z0-9-]")
NAME_CHARS = re.compile(r"[a-z0-9-]")
PLAIN_CHARS = re.compile(r"[A-Za-z0-9._-]")


def read_tag_attributes(tag: str) -> dict:
    if not isinstance(tag, str):
        raise ValueError("the tag must be a string")
    size = len(tag)
    if size == 0 or tag[0] != "[":
        raise ValueError("the tag must open with a left square bracket")
    at = 1

    cut = at
    while at < size and STEM_CHARS.fullmatch(tag[at]):
        at += 1
    stem = tag[cut:at]
    if STEM.fullmatch(stem) is None:
        raise ValueError("the stem breaks its shape: " + stem)

    marks = []
    settled = {}

    while True:
        if at >= size:
            raise ValueError("the tag never closes")
        if tag[at] == "]":
            at += 1
            break
        if tag[at] != " ":
            raise ValueError("a stray character sits where a space belongs: " + tag[at])
        at += 1
        if at >= size:
            raise ValueError("the tag never closes")
        if tag[at] == " ":
            raise ValueError("two spaces running")
        if tag[at] == "]":
            raise ValueError("a space stands before the closing bracket")

        cut = at
        while at < size and NAME_CHARS.fullmatch(tag[at]):
            at += 1
        name = tag[cut:at]
        if NAME.fullmatch(name) is None:
            raise ValueError("a mark name breaks its shape: " + name)

        setting = ""
        if at < size and tag[at] == "=":
            at += 1
            if at >= size:
                raise ValueError("an equals sign with no setting after it")
            fence = tag[at]
            if fence in ('"', "'"):
                at += 1
                out = ""
                while True:
                    if at >= size:
                        raise ValueError("a fence is never closed")
                    ch = tag[at]
                    if ch == "\\":
                        nxt = tag[at + 1] if at + 1 < size else ""
                        if nxt != fence and nxt != "\\":
                            raise ValueError(
                                "a backslash stands before something it may not"
                            )
                        out += nxt
                        at += 2
                        continue
                    if ch == fence:
                        at += 1
                        break
                    out += ch
                    at += 1
                setting = out
            else:
                cut = at
                while at < size and PLAIN_CHARS.fullmatch(tag[at]):
                    at += 1
                setting = tag[cut:at]
                if setting == "":
                    raise ValueError("an equals sign with no setting after it")

        if name in settled:
            if settled[name] != setting:
                raise ValueError(
                    "the name " + name + " is carried twice with different settings"
                )
        else:
            settled[name] = setting
            marks.append({"name": name, "setting": setting})

    if at != size:
        raise ValueError("something follows the closing bracket")
    return {"stem": stem, "marks": marks}
