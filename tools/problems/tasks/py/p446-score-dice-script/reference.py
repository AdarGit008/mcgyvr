import re

SIZES = frozenset({4, 6, 8, 10, 12, 20})
GROUP = re.compile(r"(\d+)d(\d+)(!?)")
WHOLE = re.compile(r"\d+")


def score_dice_script(script: str, rolls: list) -> int:
    if not isinstance(script, str):
        raise ValueError("the script must be a string")
    if script == "":
        raise ValueError("the script is empty")
    if not isinstance(rolls, list):
        raise ValueError("the rolls must be a list")

    state = {"drawn": 0}

    def draw(size: int) -> int:
        if state["drawn"] >= len(rolls):
            raise ValueError("the rolls run out")
        roll = rolls[state["drawn"]]
        state["drawn"] += 1
        if isinstance(roll, bool) or not isinstance(roll, int):
            raise ValueError(f"{roll} is not a roll of a {size}-sided die")
        if roll < 1 or roll > size:
            raise ValueError(f"{roll} is not a roll of a {size}-sided die")
        return roll

    pieces = re.split(r"([+-])", script)
    total = 0
    sign = 1
    for at, term in enumerate(pieces):
        if at % 2 == 1:
            sign = 1 if term == "+" else -1
            continue
        if term == "":
            raise ValueError("the script has an empty term")
        if WHOLE.fullmatch(term):
            value = int(term)
        else:
            found = GROUP.fullmatch(term)
            if found is None:
                raise ValueError(f"cannot read the term {term}")
            count = int(found.group(1))
            size = int(found.group(2))
            if count < 1 or count > 20:
                raise ValueError(f"a count of {count} is outside 1 to 20")
            if size not in SIZES:
                raise ValueError(f"there is no {size}-sided die")
            open_ended = found.group(3) == "!"
            value = 0
            for _ in range(count):
                roll = draw(size)
                value += roll
                while open_ended and roll == size:
                    roll = draw(size)
                    value += roll
        total += sign * value

    if state["drawn"] != len(rolls):
        raise ValueError(f"{len(rolls) - state['drawn']} rolls were left undrawn")
    return total
