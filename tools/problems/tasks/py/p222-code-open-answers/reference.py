import re

PHRASE = re.compile(r"[a-z0-9]+(?: [a-z0-9]+)*")


def _runs_inside(words: list, phrase: list) -> bool:
    span = len(phrase)
    for start in range(len(words) - span + 1):
        if words[start : start + span] == phrase:
            return True
    return False


def code_open_answers(rules: list, answers: list) -> dict:
    if not isinstance(rules, list) or not rules:
        raise ValueError("the rules must be a non-empty list")
    codes = []
    phrases = []
    already = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("a rule must be a mapping")
        code = rule.get("code")
        phrase = rule.get("phrase")
        if not isinstance(code, str) or not code:
            raise ValueError("a code must be a non-empty string")
        if not isinstance(phrase, str) or PHRASE.fullmatch(phrase) is None:
            raise ValueError("a phrase must be lowercase words joined by one space")
        if phrase in already:
            raise ValueError("two rules share a phrase")
        already.add(phrase)
        codes.append(code)
        phrases.append(phrase.split(" "))
    if not isinstance(answers, list):
        raise ValueError("the answers must be a list")
    order = []
    count = {}
    for code in codes:
        if code not in count:
            count[code] = 0
            order.append(code)
    loose = []
    for answer in answers:
        if not isinstance(answer, str):
            raise ValueError("an answer must be a string")
        tidy = re.sub(r"[^a-z0-9]+", " ", answer.lower()).strip()
        words = tidy.split(" ") if tidy else []
        taken = -1
        for at, phrase in enumerate(phrases):
            if _runs_inside(words, phrase):
                taken = at
                break
        if taken < 0:
            loose.append(tidy)
        else:
            count[codes[taken]] += 1
    return {
        "tally": [{"code": code, "count": count[code]} for code in order],
        "loose": loose,
    }
