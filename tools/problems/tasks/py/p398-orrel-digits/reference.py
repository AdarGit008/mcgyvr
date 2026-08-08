def orrel_digits(value: int) -> str:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("orrel_digits expects a whole number")
    if abs(value) > 1000000:
        raise ValueError("the quantity's magnitude passes one million")
    marks = "oiy"
    if value == 0:
        return "o"
    rest = value
    spelling = ""
    while rest != 0:
        place = rest % 3
        spelling = marks[place] + spelling
        rest = (rest - place) // -3
    return spelling
