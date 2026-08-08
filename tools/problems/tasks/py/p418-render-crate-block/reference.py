import re

NAME = re.compile(r"[a-z]+")


def _is_flat(value):
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, str))


def _pad(level):
    return ".." * level


def _draw_flat(value):
    if isinstance(value, int):
        return str(value)
    if re.search(r"[<>\n]", value) is not None:
        raise ValueError("a string may hold no line break and no angle bracket")
    return "<" + value + ">"


def _order(names):
    return sorted(names, key=lambda name: (len(name), name))


def _draw(value, level):
    if isinstance(value, list):
        if not value:
            return [_pad(level) + "[]"]
        lines = [_pad(level) + "["]
        for item in value:
            if _is_flat(item):
                lines.append(_pad(level + 1) + _draw_flat(item))
            elif isinstance(item, (list, dict)):
                lines.extend(_draw(item, level + 1))
            else:
                raise ValueError("a value must be a number, a string, a list or a crate")
        lines.append(_pad(level) + "]")
        return lines
    if not isinstance(value, dict):
        raise ValueError("a value must be a number, a string, a list or a crate")
    names = list(value)
    for name in names:
        if not isinstance(name, str) or NAME.fullmatch(name) is None:
            raise ValueError("a field name is small letters only")
    if not names:
        return [_pad(level) + "{}"]
    flat = _order([name for name in names if _is_flat(value[name])])
    deep = _order([name for name in names if not _is_flat(value[name])])
    lines = [_pad(level) + "{"]
    for name in flat + deep:
        held = value[name]
        if _is_flat(held):
            lines.append(_pad(level + 1) + name + " -> " + _draw_flat(held))
        elif isinstance(held, (list, dict)):
            lines.append(_pad(level + 1) + name + " ->")
            lines.extend(_draw(held, level + 2))
        else:
            raise ValueError("a value must be a number, a string, a list or a crate")
    lines.append(_pad(level) + "}")
    return lines


def render_crate_block(crate: dict) -> str:
    if not isinstance(crate, dict):
        raise ValueError("the argument must be a crate")
    return "\n".join(_draw(crate, 0))
