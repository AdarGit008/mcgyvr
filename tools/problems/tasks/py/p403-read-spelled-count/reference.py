SMALL = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def _small_value(word):
    return SMALL.index(word) if word in SMALL else -1


def _tens_value(word):
    return 20 + 10 * TENS.index(word) if word in TENS else -1


def _tail_value(word):
    if "-" in word:
        parts = word.split("-")
        if len(parts) != 2:
            raise ValueError("a hyphen joins exactly two spellings")
        tens = _tens_value(parts[0])
        unit = _small_value(parts[1])
        if tens == -1 or unit < 1 or unit > 9:
            raise ValueError("bad hyphenated pair " + word)
        return tens + unit
    tens = _tens_value(word)
    if tens != -1:
        return tens
    unit = _small_value(word)
    if unit == 0:
        raise ValueError("zero may only stand alone")
    if unit == -1:
        raise ValueError("unknown word " + word)
    return unit


def _block_value(words):
    if not words:
        raise ValueError("a block may not be empty")
    index = 0
    total = 0
    if len(words) >= 2 and words[1] == "hundred":
        head = _small_value(words[0])
        if head < 1 or head > 9:
            raise ValueError("hundred wants a one-to-nine spelling ahead of it")
        total += head * 100
        index = 2
    elif words[0] == "hundred":
        raise ValueError("hundred wants a one-to-nine spelling ahead of it")
    tail = words[index:]
    if len(tail) > 1:
        raise ValueError("a tail is one word at most")
    if len(tail) == 1:
        if tail[0] == "hundred":
            raise ValueError("hundred appears twice in one block")
        total += _tail_value(tail[0])
    return total


def read_spelled_count(phrase: str) -> int:
    if not isinstance(phrase, str):
        raise ValueError("read_spelled_count expects a string")
    if phrase == "" or phrase != phrase.strip() or "  " in phrase:
        raise ValueError("the phrase is not single-blank separated words")
    words = phrase.split(" ")
    if words == ["zero"]:
        return 0
    scales = words.count("thousand")
    if scales > 1:
        raise ValueError("thousand appears twice")
    if scales == 0:
        return _block_value(words)
    at = words.index("thousand")
    left = words[:at]
    right = words[at + 1 :]
    if not left:
        raise ValueError("thousand wants a block ahead of it")
    high = _block_value(left) * 1000
    return high if not right else high + _block_value(right)
