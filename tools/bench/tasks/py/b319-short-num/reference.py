def short_num(value: int) -> str:
    for size, suffix in ((1000000, "m"), (1000, "k")):
        if value >= size:
            tenths = value * 10 // size
            return str(tenths // 10) + "." + str(tenths % 10) + suffix
    return str(value)
