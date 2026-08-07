def mirror_step_run(width: int) -> dict:
    if not isinstance(width, int) or isinstance(width, bool):
        raise ValueError("width must be a whole number")
    if width < 1 or width > 12:
        raise ValueError("width lies within one through twelve")
    words = [""]
    for _ in range(width):
        grown = ["0" + word for word in words]
        grown += ["1" + word for word in reversed(words)]
        words = grown
    flips = []
    for before, after in zip(words, words[1:]):
        for column in range(width):
            if before[column] != after[column]:
                flips.append(column + 1)
                break
    return {"words": words, "flips": flips}
