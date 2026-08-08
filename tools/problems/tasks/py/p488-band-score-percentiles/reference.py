def _whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def band_score_percentiles(sitters: list, cuts: list, names: list) -> dict:
    if not isinstance(sitters, list) or len(sitters) == 0:
        raise ValueError("sitters must be a list holding at least one sitter")
    if not isinstance(cuts, list) or len(cuts) == 0:
        raise ValueError("cuts must be a list holding at least one cut")
    for index, cut in enumerate(cuts):
        if not _whole(cut, 1) or cut > 99:
            raise ValueError("every cut must be a whole number from 1 to 99")
        if index > 0 and cut <= cuts[index - 1]:
            raise ValueError("the cuts must strictly rise")
    if not isinstance(names, list) or len(names) != len(cuts) + 1:
        raise ValueError("the names must be one more in number than the cuts")
    heard = set()
    for name in names:
        if not isinstance(name, str) or name == "":
            raise ValueError("every name must be a non-empty string")
        if name in heard:
            raise ValueError(f"the name {name} is listed twice")
        heard.add(name)

    seen = set()
    marks = []
    for sitter in sitters:
        if not isinstance(sitter, dict):
            raise ValueError("each sitter must be a record")
        tag = sitter.get("tag")
        if not isinstance(tag, str) or tag == "":
            raise ValueError("tag must be a non-empty string")
        if tag in seen:
            raise ValueError(f"two sitters answer to the tag {tag}")
        seen.add(tag)
        if not _whole(sitter.get("score"), 0):
            raise ValueError("score must be a whole number of nought or more")
        marks.append((tag, sitter["score"]))

    count = [0] * len(names)
    rows = []
    for tag, score in marks:
        below = sum(1 for _, other in marks if other < score)
        stand = (100 * below) // len(marks)
        place = sum(1 for cut in cuts if cut <= stand)
        count[place] += 1
        rows.append({"tag": tag, "stand": stand, "band": names[place]})

    tally = [
        {"band": name, "count": count[index]} for index, name in enumerate(names)
    ]
    return {"rows": rows, "tally": tally}
