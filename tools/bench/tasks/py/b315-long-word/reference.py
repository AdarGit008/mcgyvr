def long_word(sentence: str) -> str:
    best = ""
    for word in sentence.split():
        if len(word) > len(best):
            best = word
    return best
