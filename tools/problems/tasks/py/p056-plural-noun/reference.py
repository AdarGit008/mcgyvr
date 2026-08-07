def plural_noun(word: str) -> str:
    if not isinstance(word, str):
        raise ValueError("plural_noun expects a string")
    if word == "" or not all("a" <= ch <= "z" for ch in word):
        raise ValueError("expected lowercase letters a-z only")
    irregular = {
        "child": "children",
        "person": "people",
        "foot": "feet",
        "mouse": "mice",
        "sheep": "sheep",
    }
    if word in irregular:
        return irregular[word]
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if len(word) >= 2 and word.endswith("y") and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith("fe"):
        return word[:-2] + "ves"
    if word.endswith("f"):
        return word[:-1] + "ves"
    return word + "s"
