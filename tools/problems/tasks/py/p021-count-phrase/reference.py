def count_phrase(tokens: list[str], phrase: str) -> int:
    if not isinstance(phrase, str) or phrase.strip() == "":
        raise ValueError("phrase must contain at least one word")
    words = [word.lower() for word in phrase.split(" ") if word != ""]
    lowered = [token.lower() for token in tokens]
    count = 0
    i = 0
    span = len(words)
    while i + span <= len(lowered):
        if lowered[i : i + span] == words:
            count += 1
            i += span
        else:
            i += 1
    return count
