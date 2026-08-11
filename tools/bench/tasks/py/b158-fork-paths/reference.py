import re

def fork_paths(pattern: str) -> list:
    if not isinstance(pattern, str) or pattern == "":
        raise ValueError("pattern must be a non-empty string")
    def expand(segs):
        if not segs:
            return [[]]
        found = re.fullmatch(r"\{([^{}]+)\}", segs[0])
        options = found.group(1).split(",") if found else [segs[0]]
        for option in options:
            if option == "" or re.search(r"[{},]", option):
                raise ValueError("malformed segment")
        return [[option, *tail] for option in options for tail in expand(segs[1:])]
    return ["/".join(parts) for parts in expand(pattern.split("/"))]
