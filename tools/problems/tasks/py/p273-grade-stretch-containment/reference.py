def grade_containment(source: list[str], draft: list[str], span: int) -> int:
    if not isinstance(span, int) or isinstance(span, bool) or span <= 0:
        raise ValueError("span must be a positive whole number")

    def vet(words, label):
        if not isinstance(words, list):
            raise ValueError(label + " must be a list")
        for word in words:
            if not isinstance(word, str) or not word:
                raise ValueError(label + " holds something that is not a word")

    vet(source, "source")
    vet(draft, "draft")
    if len(draft) < span:
        raise ValueError("the draft holds fewer words than span")

    tally: dict[str, int] = {}
    for i in range(len(source) - span + 1):
        stretch = " ".join(source[i : i + span])
        tally[stretch] = tally.get(stretch, 0) + 1

    matched = 0
    total = 0
    for i in range(len(draft) - span + 1):
        total += 1
        stretch = " ".join(draft[i : i + span])
        if tally.get(stretch, 0) > 0:
            tally[stretch] -= 1
            matched += 1
    return matched * 1000 // total
