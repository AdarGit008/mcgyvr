"""The track each span is drawn on."""


def assign_track_columns(spans: list) -> list:
    if not isinstance(spans, list):
        raise ValueError("spans must be a list")
    labels = set()
    for span in spans:
        if not isinstance(span, dict):
            raise ValueError("every span must be a mapping")
        label = span.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError("every span needs a non-empty label")
        first = span.get("first")
        last = span.get("last")
        for edge in (first, last):
            if not isinstance(edge, int) or isinstance(edge, bool):
                raise ValueError(f"span {label} has rows that are not whole numbers")
        if first < 0:
            raise ValueError(f"span {label} starts before row zero")
        if last < first:
            raise ValueError(f"span {label} ends before it starts")
        if label in labels:
            raise ValueError(f"two spans share the label {label}")
        labels.add(label)

    placed = []
    tracks = []
    for span in spans:
        busy = set()
        for other in placed:
            if span["first"] <= other["last"] and span["last"] >= other["first"]:
                busy.add(other["track"])
        track = 0
        while track in busy:
            track += 1
        placed.append({"first": span["first"], "last": span["last"], "track": track})
        tracks.append(track)
    return tracks
