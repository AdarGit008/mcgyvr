def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def replay_agenda_boxes(items: list, slack: int) -> dict:
    if not _whole(slack) or slack < 0:
        raise ValueError("the slack is not a whole number at nought or above")
    if not isinstance(items, list):
        raise ValueError("replay_agenda_boxes expects a list of items")

    titles = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("an item is not a record")
        if sorted(item) != ["actual", "planned", "rule", "title"]:
            raise ValueError("an item's keys are not exactly the four named")
        title = item["title"]
        if not isinstance(title, str) or not title:
            raise ValueError("a title is not a non-empty string")
        if title in titles:
            raise ValueError("two items share a title")
        titles.add(title)
        if not _whole(item["planned"]) or item["planned"] < 1:
            raise ValueError("planned is not a whole number above nought")
        if not _whole(item["actual"]) or item["actual"] < 0:
            raise ValueError("actual is not a whole number at nought or above")
        if item["rule"] not in ("absorb", "defer"):
            raise ValueError("a rule is neither absorb nor defer")

    boxes = [item["planned"] for item in items]
    log = []
    carry = []
    clock = 0
    spare = slack
    unfunded = 0

    for index, item in enumerate(items):
        title = item["title"]
        actual = item["actual"]
        box = boxes[index]
        start = clock

        if item["rule"] == "defer" and actual > box:
            clock = start + box
            log.append(f"{title} {start} {clock} cut")
            carry.append(f"{title} {actual - box}")
            continue

        clock = start + actual
        if actual < box:
            spare += box - actual
            log.append(f"{title} {start} {clock} under")
            continue
        if actual == box:
            log.append(f"{title} {start} {clock} exact")
            continue

        rest = actual - box
        drawn = min(rest, spare)
        spare -= drawn
        rest -= drawn
        following = index + 1
        while following < len(boxes) and rest > 0:
            given = min(rest, boxes[following] - 1)
            boxes[following] -= given
            rest -= given
            following += 1
        unfunded += rest
        log.append(f"{title} {start} {clock} over")

    return {
        "finish": clock,
        "spare": spare,
        "unfunded": unfunded,
        "log": log,
        "carry": carry,
    }
