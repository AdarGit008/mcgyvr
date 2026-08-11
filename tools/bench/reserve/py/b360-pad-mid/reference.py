def pad_side(count: int) -> str:
    if count <= 0:
        return ""
    return " " * count


def pad_mid(word: str, width: int) -> str:
    spare = width - len(word)
    left = spare // 2
    return pad_side(left) + word + pad_side(spare - left)
