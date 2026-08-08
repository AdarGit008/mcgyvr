def smallest_arrangement(counts: list) -> str:
    if not isinstance(counts, list) or not 1 <= len(counts) <= 4:
        raise ValueError("counts must be a list of one to four integers")
    for count in counts:
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > 12
        ):
            raise ValueError("each count must be an integer from 0 to 12")
    total = sum(counts)
    if total == 0:
        raise ValueError("at least one count must be positive")

    width = len(counts)
    memo = {}

    def finishable(state, last, run):
        if sum(state) == 0:
            return True
        key = (state, last, run)
        if key in memo:
            return memo[key]
        possible = False
        for i in range(width):
            if state[i] == 0 or (i == last and run == 2):
                continue
            nxt = list(state)
            nxt[i] -= 1
            if finishable(tuple(nxt), i, run + 1 if i == last else 1):
                possible = True
                break
        memo[key] = possible
        return possible

    state = tuple(counts)
    last = -1
    run = 0
    letters = []
    for _ in range(total):
        for i in range(width):
            if state[i] == 0 or (i == last and run == 2):
                continue
            nxt = list(state)
            nxt[i] -= 1
            next_run = run + 1 if i == last else 1
            if finishable(tuple(nxt), i, next_run):
                letters.append(chr(97 + i))
                state = tuple(nxt)
                run = next_run
                last = i
                break
        else:
            raise ValueError("no arrangement avoids a triple run")
    return "".join(letters)
