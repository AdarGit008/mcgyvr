from collections import deque


def _name_list(value, what: str, allow_empty: bool) -> list:
    if not isinstance(value, list):
        raise ValueError(what + " must be a list")
    if not value and not allow_empty:
        raise ValueError(what + " must not be empty")
    out = []
    seen = set()
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(what + " holds something that is not a non-empty string")
        if item in seen:
            raise ValueError(what + " names " + item + " twice")
        seen.add(item)
        out.append(item)
    return out


def fold_machine(machine: dict) -> dict:
    if not isinstance(machine, dict):
        raise ValueError("a machine must be a mapping")
    alphabet = _name_list(machine.get("alphabet"), "the alphabet", False)
    states = _name_list(machine.get("states"), "the state list", False)
    state_set = set(states)
    symbol_set = set(alphabet)
    start = machine.get("start")
    if not isinstance(start, str) or start not in state_set:
        raise ValueError("the start is not a listed state")
    accepting = set(_name_list(machine.get("accepting"), "the accepting list", True))
    for name in accepting:
        if name not in state_set:
            raise ValueError(name + " accepts but is not a listed state")
    moves = machine.get("moves")
    if not isinstance(moves, list):
        raise ValueError("the moves must be a list")
    delta = {state: {} for state in states}
    for move in moves:
        if not isinstance(move, list) or len(move) != 3:
            raise ValueError("a move is three elements")
        origin, symbol, target = move
        if not isinstance(origin, str) or origin not in state_set:
            raise ValueError("a move leaves an undeclared state")
        if not isinstance(target, str) or target not in state_set:
            raise ValueError("a move lands on an undeclared state")
        if not isinstance(symbol, str) or symbol not in symbol_set:
            raise ValueError("a move carries an undeclared symbol")
        if symbol in delta[origin]:
            raise ValueError(origin + " has two moves on " + symbol)
        delta[origin][symbol] = target
    for state in states:
        for symbol in alphabet:
            if symbol not in delta[state]:
                raise ValueError(state + " has no move on " + symbol)

    reached = {start}
    frontier = deque([start])
    while frontier:
        state = frontier.popleft()
        for symbol in alphabet:
            nxt = delta[state][symbol]
            if nxt not in reached:
                reached.add(nxt)
                frontier.append(nxt)
    live = [state for state in states if state in reached]

    block = {state: (1 if state in accepting else 0) for state in live}
    blocks = len(set(block.values()))
    while True:
        seen: dict = {}
        nxt_block = {}
        for state in live:
            parts = [str(block[delta[state][symbol]]) for symbol in alphabet]
            signature = str(block[state]) + "|" + ",".join(parts)
            if signature not in seen:
                seen[signature] = len(seen)
            nxt_block[state] = seen[signature]
        block = nxt_block
        if len(seen) == blocks:
            break
        blocks = len(seen)

    representative: dict = {}
    for state in live:
        representative.setdefault(block[state], state)
    numbered = {block[start]: 0}
    order = [block[start]]
    index = 0
    while index < len(order):
        rep = representative[order[index]]
        for symbol in alphabet:
            target = block[delta[rep][symbol]]
            if target not in numbered:
                numbered[target] = len(order)
                order.append(target)
        index += 1

    accepts = []
    folded = []
    for position, group in enumerate(order):
        rep = representative[group]
        if rep in accepting:
            accepts.append(position)
        for symbol in alphabet:
            target = block[delta[rep][symbol]]
            folded.append([position, symbol, numbered[target]])
    return {
        "size": len(order),
        "start": 0,
        "accepting": accepts,
        "moves": folded,
    }
