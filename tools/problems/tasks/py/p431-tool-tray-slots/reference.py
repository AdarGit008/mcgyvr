VERBS = ("touch", "pin", "drop")


def fold_tool_tray(slots: int, actions: list[list[str]]) -> list[str]:
    if not isinstance(slots, int) or isinstance(slots, bool) or slots < 1:
        raise ValueError("slots must be a whole number of at least 1")
    if not isinstance(actions, list):
        raise ValueError("the actions must be a list of pairs")

    order: list[str] = []
    stuck: set[str] = set()

    for action in actions:
        if not isinstance(action, (list, tuple)) or len(action) != 2:
            raise ValueError("an action is a [verb, name] pair")
        verb, name = action
        if not isinstance(verb, str) or verb not in VERBS:
            raise ValueError("a verb is one of touch, pin and drop")
        if not isinstance(name, str) or not name or "*" in name:
            raise ValueError("a name must be a non-empty string free of asterisks")

        inside = name in order
        if verb == "touch":
            if inside:
                order.remove(name)
                order.append(name)
                continue
            if len(order) >= slots:
                victim = next((held for held in order if held not in stuck), None)
                if victim is None:
                    continue
                order.remove(victim)
                stuck.discard(victim)
            order.append(name)
        elif verb == "pin":
            if inside:
                stuck.add(name)
        elif inside:
            order.remove(name)
            stuck.discard(name)

    return [f"*{name}" if name in stuck else name for name in reversed(order)]
