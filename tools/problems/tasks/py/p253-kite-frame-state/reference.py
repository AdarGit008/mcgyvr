def kite_frame_state(rallies: list[str]) -> dict:
    if not isinstance(rallies, list):
        raise ValueError("kite_frame_state expects a list of rally winners")
    score = {"left": 0, "right": 0}
    winner = ""
    for rally in rallies:
        if rally not in ("left", "right"):
            raise ValueError(f"unknown side {rally!r}")
        if winner:
            continue
        score[rally] += 1
        other = "right" if rally == "left" else "left"
        ahead = score[rally] - score[other]
        if (score[rally] >= 15 and ahead >= 2) or score[rally] >= 20:
            winner = rally
    return {"left": score["left"], "right": score["right"], "winner": winner}
