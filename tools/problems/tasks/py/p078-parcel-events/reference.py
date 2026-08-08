_MOVES = {
    "load": {"accepted": "in_transit"},
    "deliver": {"in_transit": "delivered"},
    "bounce": {"delivered": "returned"},
    "lose": {"accepted": "lost", "in_transit": "lost"},
}


def fold_parcels(events: list) -> dict:
    states: dict = {}
    for i, event in enumerate(events):
        kind = event["type"]
        parcel = event["parcel"]
        if kind == "accept":
            if parcel in states:
                raise ValueError(f"event {i}: parcel already accepted")
            states[parcel] = "accepted"
            continue
        moves = _MOVES.get(kind)
        if moves is None:
            raise ValueError(f"event {i}: unknown type {kind}")
        if parcel not in states:
            raise ValueError(f"event {i}: unknown parcel {parcel}")
        after = moves.get(states[parcel])
        if after is None:
            raise ValueError(
                f"event {i}: invalid transition {kind} from {states[parcel]}"
            )
        states[parcel] = after
    return states
