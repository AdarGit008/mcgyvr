import re


def pick_snippet(query, sentences):
    def words_of(text):
        return re.findall(r"[a-z0-9]+", text.lower())

    if not isinstance(query, str):
        raise ValueError("query must be a string")
    wanted = set(words_of(query))
    if not wanted:
        raise ValueError("query holds no words")
    if not isinstance(sentences, list) or not sentences:
        raise ValueError("sentences must be a non-empty list")
    best_at = -1
    best_score = 0
    best_size = 0
    for index, sentence in enumerate(sentences):
        if not isinstance(sentence, str) or not sentence:
            raise ValueError("every sentence must be a non-empty string")
        found = words_of(sentence)
        score = len(wanted & set(found))
        if score == 0:
            continue
        if score > best_score:
            best_score = score
            best_size = len(found)
            best_at = index
        elif score == best_score and len(found) < best_size:
            best_size = len(found)
            best_at = index
    if best_at == -1:
        raise ValueError("no sentence holds a query word")
    return sentences[best_at]
