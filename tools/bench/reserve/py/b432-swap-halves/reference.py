def swap_halves(text: str) -> str:
    cut = (len(text) + 1) // 2
    return text[cut:] + text[:cut]
