def repeat_words(text, least):
    if not isinstance(text, str):
        raise ValueError("repeat_words expects a string")
    if isinstance(least, bool) or not isinstance(least, int) or least < 1:
        raise ValueError("least must be a positive whole number")
    if any(ch != " " and not ("a" <= ch.lower() <= "z") for ch in text):
        raise ValueError("text may hold only ASCII letters and spaces")
    counts = {}
    for word in text.split():
        folded = word.lower()
        counts[folded] = counts.get(folded, 0) + 1
    return [word for word, seen in counts.items() if seen >= least]
