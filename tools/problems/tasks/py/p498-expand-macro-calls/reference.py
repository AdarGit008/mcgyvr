import re

_NAME = re.compile(r"[a-z][a-z0-9]*")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def expand_macro_calls(macros: list, source: str, bound: int) -> str:
    if not _whole(bound) or bound < 1:
        raise ValueError("the bound is not whole or falls below one")
    if not isinstance(source, str):
        raise ValueError("the source is not a string")
    if not isinstance(macros, list):
        raise ValueError("expand_macro_calls expects a list of macros")

    table = {}
    for macro in macros:
        if not isinstance(macro, dict):
            raise ValueError("a macro is not a record")
        if sorted(macro) != ["arity", "body", "name"]:
            raise ValueError("a macro's keys are not exactly the three named")
        name = macro["name"]
        if not isinstance(name, str) or _NAME.fullmatch(name) is None:
            raise ValueError("a macro name is malformed")
        if name in table:
            raise ValueError("two macros answer to one name")
        arity = macro["arity"]
        if not _whole(arity) or arity < 0 or arity > 9:
            raise ValueError("an arity is not whole or falls outside nought through nine")
        if not isinstance(macro["body"], str):
            raise ValueError("a body is not a string")
        table[name] = (arity, macro["body"])

    def fill(body, args, arity):
        out = []
        at = 0
        while at < len(body):
            ch = body[at]
            if ch != "#":
                out.append(ch)
                at += 1
                continue
            nxt = body[at + 1] if at + 1 < len(body) else ""
            if nxt == "#":
                out.append("#")
                at += 2
                continue
            if nxt.isdigit() and nxt.isascii():
                place = int(nxt)
                if place < 1 or place > arity:
                    raise ValueError("a body names a place the macro's arity does not reach")
                out.append(args[place - 1])
                at += 2
                continue
            raise ValueError("a stray hash stands in a body")
        return "".join(out)

    def walk(text, depth):
        out = []
        at = 0
        while at < len(text):
            ch = text[at]
            if ch != "@":
                out.append(ch)
                at += 1
                continue
            if at + 1 < len(text) and text[at + 1] == "@":
                out.append("@")
                at += 2
                continue
            head = text[at + 1] if at + 1 < len(text) else ""
            if not ("a" <= head <= "z"):
                raise ValueError("a stray at sign stands in the text")
            end = at + 1
            while end < len(text) and ("a" <= text[end] <= "z" or text[end] in "0123456789"):
                end += 1
            name = text[at + 1 : end]

            args = []
            if end < len(text) and text[end] == "{":
                pieces = []
                piece = []
                nest = 1
                cursor = end + 1
                while cursor < len(text) and nest > 0:
                    inner = text[cursor]
                    if inner == "{":
                        nest += 1
                        piece.append(inner)
                    elif inner == "}":
                        nest -= 1
                        if nest > 0:
                            piece.append(inner)
                    elif inner == "|" and nest == 1:
                        pieces.append("".join(piece))
                        piece = []
                    else:
                        piece.append(inner)
                    cursor += 1
                if nest != 0:
                    raise ValueError("a brace is never closed")
                pieces.append("".join(piece))
                args = pieces
                at = cursor
            else:
                at = end

            if name not in table:
                raise ValueError("the text calls a macro that was never declared")
            arity, body = table[name]
            if len(args) != arity:
                raise ValueError("a call's argument count differs from the arity")
            if depth + 1 > bound:
                raise ValueError("the expansion runs deeper than the bound")
            out.append(walk(fill(body, args, arity), depth + 1))
        return "".join(out)

    return walk(source, 0)
