def token_fold(phrase: str) -> str:
    folded = []
    for word in phrase.split():
        folded.append(word[0].upper() + word[1:].lower())
    return " ".join(folded)
