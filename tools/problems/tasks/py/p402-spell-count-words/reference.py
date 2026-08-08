SMALL = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)

ROUND = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)


def _under_thousand(value: int) -> str:
    if value < 20:
        return SMALL[value]
    if value < 100:
        round_word = ROUND[value // 10]
        leftover = value % 10
        return round_word if leftover == 0 else round_word + "-" + SMALL[leftover]
    head = SMALL[value // 100] + " hundred"
    leftover = value % 100
    return head if leftover == 0 else head + " and " + _under_thousand(leftover)


def spell_count_words(count: int) -> str:
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("spell_count_words expects a whole number")
    if count < 0 or count > 999999:
        raise ValueError("count is outside 0 through 999999")
    if count < 1000:
        return _under_thousand(count)
    head = _under_thousand(count // 1000) + " thousand"
    leftover = count % 1000
    if leftover == 0:
        return head
    return head + (" and " if leftover < 100 else " ") + _under_thousand(leftover)
