from solution import fold_transcript


def rejects(lines):
    try:
        fold_transcript(lines)
    except Exception:
        return True
    return False


assert fold_transcript([]) == [], "an empty transcript gathers nothing"
assert fold_transcript(["  ada :   the pump is dry  "]) == [{"speaker": "ada", "text": "the pump is dry"}], "one line is trimmed on both sides of the colon"
assert fold_transcript(["ada: the pump is dry", "ada: I shut the valve"]) == [{"speaker": "ada", "text": "the pump is dry I shut the valve"}], "neighbouring lines from one speaker join"
assert fold_transcript(["ada: dry", "bo: noted", "ada: refilled"]) == [{"speaker": "ada", "text": "dry"}, {"speaker": "bo", "text": "noted"}, {"speaker": "ada", "text": "refilled"}], "a speaker coming back opens a fresh block"
assert fold_transcript(["ada: dry", "ada:    ", "ada: refilled"]) == [{"speaker": "ada", "text": "dry refilled"}], "an empty line interrupts nothing"
assert fold_transcript(["bo: warning: seal at 4:15"]) == [{"speaker": "bo", "text": "warning: seal at 4:15"}], "only the first colon parts the line"
assert rejects(["no colon anywhere"]), "a line carrying no colon is rejected"
print("ok")
