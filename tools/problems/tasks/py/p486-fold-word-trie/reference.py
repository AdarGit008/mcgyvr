import re


def _shared_opening(run):
    opening = run[0]
    for word in run:
        i = 0
        while i < len(opening) and i < len(word) and opening[i] == word[i]:
            i += 1
        opening = opening[:i]
    return opening


def _by_opening_letter(run):
    buckets = {}
    for word in run:
        buckets.setdefault(word[0], []).append(word)
    return [buckets[head] for head in sorted(buckets)]


def _squeeze(run):
    if len(run) == 1:
        return run[0]
    opening = _shared_opening(run)
    tails = [word[len(opening) :] for word in run]
    parts = []
    if any(tail == "" for tail in tails):
        parts.append("-")
    for bucket in _by_opening_letter([tail for tail in tails if tail != ""]):
        parts.append(_squeeze(bucket))
    return opening + "(" + "|".join(parts) + ")"


def fold_word_trie(words: list) -> str:
    if not isinstance(words, list) or len(words) == 0:
        raise ValueError("words must be a list holding at least one word")
    seen = set()
    for word in words:
        if not isinstance(word, str):
            raise ValueError("every word must be a string")
        if word == "":
            raise ValueError("an empty word cannot be squeezed")
        if re.fullmatch(r"[a-z]+", word) is None:
            raise ValueError(f"{word} carries something other than small letters")
        if word in seen:
            raise ValueError(f"{word} turns up twice")
        seen.add(word)
    return "|".join(_squeeze(run) for run in _by_opening_letter(sorted(words)))
