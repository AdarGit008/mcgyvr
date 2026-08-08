import re


def _read_post(text):
    parts = text.split(".")
    if len(parts) != 3:
        raise ValueError("a post has exactly three numbers")
    numbers = []
    for part in parts:
        if re.fullmatch(r"[0-9]{1,2}", part) is None:
            raise ValueError("not a number: " + part)
        if len(part) == 2 and part[0] == "0":
            raise ValueError("number written with a padding zero")
        value = int(part)
        if value > 15:
            raise ValueError("number above 15")
        numbers.append(value)
    return numbers


def claim_zone(claims: list, where: str) -> str:
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    if not isinstance(where, str):
        raise ValueError("where must be a string")
    spot = _read_post(where)
    seen = set()
    best_depth = -1
    best_name = ""
    for claim in claims:
        if not isinstance(claim, str):
            raise ValueError("every claim must be a string")
        space = claim.find(" ")
        if space == -1:
            raise ValueError("claim carries no name")
        stencil = claim[:space]
        name = claim[space + 1 :]
        if name == "" or " " in name:
            raise ValueError("name is empty or holds a space")
        if stencil in seen:
            raise ValueError("two claims carry the same stencil")
        seen.add(stencil)
        slash = stencil.find("/")
        if slash == -1:
            raise ValueError("stencil carries no slash")
        fixed = _read_post(stencil[:slash])
        depth_text = stencil[slash + 1 :]
        if re.fullmatch(r"[0-3]", depth_text) is None:
            raise ValueError("depth outside 0 to 3")
        depth = int(depth_text)
        for slot in range(depth, 3):
            if fixed[slot] != 0:
                raise ValueError("a number after the fixed ones is not 0")
        covers = all(fixed[slot] == spot[slot] for slot in range(depth))
        if covers and depth > best_depth:
            best_depth = depth
            best_name = name
    return best_name
