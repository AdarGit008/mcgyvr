def flag_list(line: str) -> list:
    flags = []
    for word in line.split(" "):
        if word.startswith("-"):
            flags.append(word[1:])
    return flags
