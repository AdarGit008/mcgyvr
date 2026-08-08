def fit_chargers(chargers, devices):
    taken = [False] * len(chargers)
    handed = []
    for device in devices:
        pick = -1
        for index, charger in enumerate(chargers):
            if (
                not taken[index]
                and charger["plug"] == device["plug"]
                and charger["low"] <= device["draw"] <= charger["high"]
            ):
                pick = index
                break
        if pick != -1:
            taken[pick] = True
        handed.append(pick)
    return handed
