def swipe_dedupe(swipes: list) -> list:
    kept = []
    for swipe in swipes:
        if not kept or kept[-1] != swipe:
            kept.append(swipe)
    return kept
