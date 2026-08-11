def deal_bags(parcels, caps):
    if not isinstance(parcels, list) or not isinstance(caps, list) or not caps:
        raise ValueError("deal_bags expects a parcel list and a non-empty cap list")
    for cap in caps:
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ValueError("every bag capacity must be a positive whole number")
    loads = [[] for _ in caps]
    spare = []
    bag = 0
    for parcel in parcels:
        # Pass over full bags; a whole round of them means the depot is out of room.
        passed = 0
        while passed < len(caps) and len(loads[bag]) == caps[bag]:
            bag = (bag + 1) % len(caps)
            passed += 1
        if passed == len(caps):
            spare.append(parcel)
            continue
        loads[bag].append(parcel)
        bag = (bag + 1) % len(caps)
    return {"loads": loads, "spare": spare}
