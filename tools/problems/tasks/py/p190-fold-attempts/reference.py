import re


def fold_attempts(records: list) -> list:
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    tries = {}
    for record in records:
        if not isinstance(record, str):
            raise ValueError("every record must be a string")
        pieces = record.split(" ")
        if len(pieces) != 3:
            raise ValueError("a record holds exactly three pieces")
        name, try_text, outcome = pieces
        if name == "":
            raise ValueError("empty case name")
        if re.fullmatch(r"[0-9]+", try_text) is None:
            raise ValueError("try number is not digits")
        if len(try_text) > 1 and try_text[0] == "0":
            raise ValueError("try number carries a padding zero")
        number = int(try_text)
        if number == 0:
            raise ValueError("try number is zero")
        if outcome not in ("pass", "fail"):
            raise ValueError("outcome is neither pass nor fail")
        seen = tries.setdefault(name, {})
        if number in seen:
            raise ValueError("a case repeats a try number")
        seen[number] = outcome

    settled = []
    for name in sorted(tries):
        seen = tries[name]
        for number in range(1, len(seen) + 1):
            if number not in seen:
                raise ValueError("a case skips a try number")
        outcomes = list(seen.values())
        passed = outcomes.count("pass")
        if passed == len(outcomes):
            word = "pass"
        elif passed == 0:
            word = "fail"
        else:
            word = "flake"
        settled.append(name + "=" + word)
    return settled
