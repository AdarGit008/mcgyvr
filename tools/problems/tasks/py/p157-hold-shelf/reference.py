def hold_shelf_replay(slips: list) -> list:
    queue = []
    answers = []
    for slip in slips:
        if not isinstance(slip, str):
            raise ValueError("slip must be a string")
        if slip == "serve":
            if not queue:
                answers.append("idle")
            else:
                answers.append("take:" + queue.pop(0))
        elif slip.startswith("join "):
            name = slip[5:]
            if name == "":
                raise ValueError("missing name")
            if name in queue:
                answers.append("no:again")
            else:
                queue.append(name)
                answers.append("at:" + str(len(queue)))
        elif slip.startswith("leave "):
            name = slip[6:]
            if name == "":
                raise ValueError("missing name")
            if name not in queue:
                answers.append("no:absent")
            else:
                queue.remove(name)
                answers.append("out")
        else:
            raise ValueError("bad slip")
    return answers
