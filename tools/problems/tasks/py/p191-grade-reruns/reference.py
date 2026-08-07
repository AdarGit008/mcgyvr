def grade_reruns(log: list, budget: int) -> list:
    if not isinstance(log, list):
        raise ValueError("log must be a list")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError("budget must be a whole number of at least zero")
    goes = {}
    for entry in log:
        if not isinstance(entry, str):
            raise ValueError("every entry must be a string")
        pieces = entry.split(" ")
        if len(pieces) != 2:
            raise ValueError("an entry holds exactly two pieces")
        name, mark = pieces
        if name == "":
            raise ValueError("empty job name")
        if mark not in ("green", "red"):
            raise ValueError("mark is neither green nor red")
        marks = goes.setdefault(name, [])
        if marks and marks[-1] == "green":
            raise ValueError("an entry for a job that has already gone green")
        if len(marks) == budget + 1:
            raise ValueError("more goes than the budget allows")
        marks.append(mark)

    graded = []
    for name in sorted(goes):
        marks = goes[name]
        if marks[-1] == "green":
            word = "solid" if len(marks) == 1 else "shaky"
        else:
            word = "broken" if len(marks) == budget + 1 else "dropped"
        graded.append(name + ":" + word)
    return graded
