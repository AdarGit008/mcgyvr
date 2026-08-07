def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _label(value):
    return isinstance(value, str) and bool(value)


def settle_swap_requests(board: dict, requests: list) -> dict:
    if not isinstance(board, dict):
        raise ValueError("the board is not a record")
    if sorted(board) != ["cap", "cleared", "duties", "peak", "quota"]:
        raise ValueError("the board's keys are not exactly the five named")

    duties = board["duties"]
    if not isinstance(duties, list):
        raise ValueError("the duties are not a list")
    held = {}
    for duty in duties:
        if not isinstance(duty, dict):
            raise ValueError("a duty is not a record")
        if sorted(duty) != ["day", "post", "worker"]:
            raise ValueError("a duty's keys are not exactly the three named")
        day = duty["day"]
        if not _whole(day) or day < 1:
            raise ValueError("a day is not whole or falls below one")
        if not _label(duty["post"]):
            raise ValueError("a post is not a non-empty string")
        if not _label(duty["worker"]):
            raise ValueError("a worker is not a non-empty string")
        posts = held.setdefault(day, {})
        if duty["post"] in posts:
            raise ValueError("two duties share one day and post")
        posts[duty["post"]] = duty["worker"]
    for posts in held.values():
        workers = set()
        for worker in posts.values():
            if worker in workers:
                raise ValueError("a worker opens on two posts of one day")
            workers.add(worker)

    cleared = board["cleared"]
    if not isinstance(cleared, list):
        raise ValueError("the cleared list is not a list")
    clearances = {}
    for entry in cleared:
        if not isinstance(entry, dict):
            raise ValueError("a clearance is not a record")
        if sorted(entry) != ["posts", "worker"]:
            raise ValueError("a clearance's keys are not exactly the two named")
        if not _label(entry["worker"]):
            raise ValueError("a cleared worker is not a non-empty string")
        if entry["worker"] in clearances:
            raise ValueError("two clearances name one worker")
        posts = entry["posts"]
        if not isinstance(posts, list):
            raise ValueError("a clearance's posts are not a list")
        allowed = set()
        for post in posts:
            if not _label(post):
                raise ValueError("a cleared post is not a non-empty string")
            if post in allowed:
                raise ValueError("a clearance repeats a post")
            allowed.add(post)
        clearances[entry["worker"]] = allowed
    for posts in held.values():
        for worker in posts.values():
            if worker not in clearances:
                raise ValueError("a worker on duty has no clearance entry")

    peak_list = board["peak"]
    if not isinstance(peak_list, list):
        raise ValueError("the peak days are not a list")
    peak = set()
    for day in peak_list:
        if not _whole(day) or day < 1:
            raise ValueError("a peak day is not whole or falls below one")
        if day in peak:
            raise ValueError("a peak day is listed twice")
        peak.add(day)

    cap = board["cap"]
    if not _whole(cap) or cap < 0:
        raise ValueError("the cap is not whole or falls below nought")
    quota = board["quota"]
    if not _whole(quota) or quota < 0:
        raise ValueError("the quota is not whole or falls below nought")

    if not isinstance(requests, list):
        raise ValueError("settle_swap_requests expects a list of requests")
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("a request is not a record")
        if sorted(request) != ["left", "right"]:
            raise ValueError("a request's keys are not exactly left and right")
        for side in (request["left"], request["right"]):
            if not isinstance(side, list) or len(side) != 2:
                raise ValueError("a side is not a list of exactly two entries")
            if not _whole(side[0]) or side[0] < 1:
                raise ValueError("a side's day is not whole or falls below one")
            if not _label(side[1]):
                raise ValueError("a side's post is not a non-empty string")

    tally = {}
    rulings = []

    for request in requests:
        day_left, post_left = request["left"]
        day_right, post_right = request["right"]
        one = held.get(day_left, {}).get(post_left)
        two = held.get(day_right, {}).get(post_right)

        if one is None or two is None:
            rulings.append("unknown")
            continue
        if (day_left == day_right and post_left == post_right) or one == two:
            rulings.append("same")
            continue
        if post_right not in clearances[one] or post_left not in clearances[two]:
            rulings.append("uncleared")
            continue

        def after(worker):
            days = []
            for day, posts in held.items():
                for post, sitting in posts.items():
                    now = sitting
                    if day == day_left and post == post_left:
                        now = two
                    elif day == day_right and post == post_right:
                        now = one
                    if now == worker:
                        days.append(day)
            return days

        days_one = after(one)
        days_two = after(two)
        if len(set(days_one)) != len(days_one) or len(set(days_two)) != len(days_two):
            rulings.append("clash")
            continue
        heavy_one = len([day for day in days_one if day in peak])
        heavy_two = len([day for day in days_two if day in peak])
        if heavy_one > cap or heavy_two > cap:
            rulings.append("peak")
            continue
        if tally.get(one, 0) >= quota or tally.get(two, 0) >= quota:
            rulings.append("quota")
            continue

        held[day_left][post_left] = two
        held[day_right][post_right] = one
        tally[one] = tally.get(one, 0) + 1
        tally[two] = tally.get(two, 0) + 1
        rulings.append("taken")

    roster = []
    for day in sorted(held):
        for post in sorted(held[day]):
            roster.append(f"{day} {post} {held[day][post]}")

    return {"rulings": rulings, "roster": roster}
