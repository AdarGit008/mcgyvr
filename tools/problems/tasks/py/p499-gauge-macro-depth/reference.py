import re

_NAME = re.compile(r"[a-z][a-z0-9]*")
_LOOSE = -1


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def gauge_macro_depth(macros: list, bound: int) -> list:
    if not _whole(bound) or bound < 0:
        raise ValueError("the bound is not whole or falls below nought")
    if not isinstance(macros, list):
        raise ValueError("gauge_macro_depth expects a list of macros")

    arity = {}
    calls = {}
    counts = {}
    for macro in macros:
        if not isinstance(macro, dict):
            raise ValueError("a macro is not a record")
        if sorted(macro) != ["arity", "calls", "name"]:
            raise ValueError("a macro's keys are not exactly the three named")
        name = macro["name"]
        if not isinstance(name, str) or _NAME.fullmatch(name) is None:
            raise ValueError("a macro name is malformed")
        if name in arity:
            raise ValueError("two macros answer to one name")
        taken = macro["arity"]
        if not _whole(taken) or taken < 0 or taken > 9:
            raise ValueError("an arity is not whole or falls outside nought through nine")
        made = macro["calls"]
        if not isinstance(made, list):
            raise ValueError("the calls are not a list")
        named = []
        handed = []
        for call in made:
            if not isinstance(call, list) or len(call) != 2:
                raise ValueError("a call is not a list of exactly two entries")
            if not isinstance(call[0], str) or not call[0]:
                raise ValueError("a called name is not a non-empty string")
            if not _whole(call[1]) or call[1] < 0:
                raise ValueError("a call's argument count is not whole or falls below nought")
            named.append(call[0])
            handed.append(call[1])
        arity[name] = taken
        calls[name] = named
        counts[name] = handed

    for name, named in calls.items():
        for callee, handed in zip(named, counts[name]):
            if callee not in arity:
                raise ValueError("a call names a macro that was never declared")
            if handed != arity[callee]:
                raise ValueError("a call hands over arguments the called macro does not take")

    state = {}
    memo = {}

    def resolve(name):
        if state.get(name) == 1:
            return _LOOSE
        if state.get(name) == 2:
            return memo[name]
        state[name] = 1
        deepest = 0
        loose = False
        for callee in calls[name]:
            found = resolve(callee)
            if found == _LOOSE:
                loose = True
            elif found + 1 > deepest:
                deepest = found + 1
        state[name] = 2
        memo[name] = _LOOSE if loose else deepest
        return memo[name]

    lines = []
    for name in sorted(arity):
        found = resolve(name)
        if found == _LOOSE:
            lines.append(f"{name} cyclic")
        elif found > bound:
            lines.append(f"{name} over")
        else:
            lines.append(f"{name} {found}")
    return lines
