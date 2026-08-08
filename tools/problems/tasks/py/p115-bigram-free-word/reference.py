def smallest_free_word(n: int, k: int, banned: list) -> str:
    if not isinstance(n, int) or isinstance(n, bool) or n < 1 or n > 12:
        raise ValueError("n must be a positive integer of at most 12")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1 or k > 6:
        raise ValueError("k must be an integer from 1 to 6")
    if not isinstance(banned, list):
        raise ValueError("banned must be a list")
    letters = [chr(97 + i) for i in range(k)]
    blocked = set()
    for pair in banned:
        if (
            not isinstance(pair, str)
            or len(pair) != 2
            or pair[0] not in letters
            or pair[1] not in letters
        ):
            raise ValueError("banned entries are two-letter strings in the alphabet")
        blocked.add(pair)

    memo = {}

    def extendable(previous, remaining):
        if remaining == 0:
            return True
        key = (previous, remaining)
        if key in memo:
            return memo[key]
        possible = False
        for letter in letters:
            if previous and previous + letter in blocked:
                continue
            if extendable(letter, remaining - 1):
                possible = True
                break
        memo[key] = possible
        return possible

    word = []
    previous = ""
    for position in range(n):
        for letter in letters:
            if previous and previous + letter in blocked:
                continue
            if extendable(letter, n - position - 1):
                word.append(letter)
                previous = letter
                break
        else:
            raise ValueError("every candidate word is blocked")
    return "".join(word)
