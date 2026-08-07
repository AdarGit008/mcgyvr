WORDS = {"pass", "flap", "halt"}


def tally_stage_retries(stages: list, budget: int) -> list:
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise ValueError("the budget must be a whole number of one or more")
    if not isinstance(stages, list):
        raise ValueError("the pipeline must be a list of stage records")

    lines = []
    seen = set()
    all_attempts = 0
    all_retries = 0
    all_flaps = 0
    all_halts = 0
    greens = 0

    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError("each stage must be a record")
        name = stage.get("name")
        if not isinstance(name, str) or name == "" or " " in name:
            raise ValueError("a stage name must be a non-empty string without spaces")
        if name in seen:
            raise ValueError("repeated stage name: " + name)
        seen.add(name)

        outcomes = stage.get("outcomes")
        if not isinstance(outcomes, list) or not outcomes:
            raise ValueError(name + " carries no outcomes")
        if len(outcomes) > budget:
            raise ValueError(name + " carries more attempts than the budget allows")
        for index, word in enumerate(outcomes):
            if word not in WORDS:
                raise ValueError(name + " carries an unknown outcome")
            if index > 0 and outcomes[index - 1] != "flap":
                raise ValueError(name + " carries an outcome after it had already ended")

        attempts = len(outcomes)
        retries = attempts - 1
        flaps = outcomes.count("flap")
        halts = outcomes.count("halt")
        last = outcomes[-1]
        verdict = "open"
        if last == "pass":
            verdict = "green"
            greens += 1
        elif last == "halt":
            verdict = "dead"
        elif attempts == budget:
            verdict = "spent"

        all_attempts += attempts
        all_retries += retries
        all_flaps += flaps
        all_halts += halts
        lines.append(
            " ".join(
                [name, str(attempts), str(retries), str(flaps), str(halts), verdict]
            )
        )

    lines.append(
        " ".join(
            [
                "*",
                str(all_attempts),
                str(all_retries),
                str(all_flaps),
                str(all_halts),
                str(greens),
            ]
        )
    )
    return lines
