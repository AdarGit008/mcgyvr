def word_tally(sentence: str) -> dict:
    tally = {}
    for word in sentence.lower().split():
        tally[word] = tally.get(word, 0) + 1
    return tally
