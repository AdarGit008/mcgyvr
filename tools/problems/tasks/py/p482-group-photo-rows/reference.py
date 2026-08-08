FAMILIES = ("upright", "oblong", "square")


def _whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def group_photo_rows(photos: list, sheet: dict) -> list:
    if not isinstance(photos, list) or len(photos) == 0:
        raise ValueError("photos must be a list holding at least one picture")
    if not isinstance(sheet, dict):
        raise ValueError("sheet must be a record")
    width = sheet.get("width")
    band = sheet.get("band")
    gap = sheet.get("gap")
    if not _whole(width, 1):
        raise ValueError("sheet width must be a whole number above nought")
    if not _whole(band, 1):
        raise ValueError("sheet band must be a whole number above nought")
    if not _whole(gap, 0):
        raise ValueError("sheet gap must be a whole number of nought or more")

    seen = set()
    kept = []
    for photo in photos:
        if not isinstance(photo, dict):
            raise ValueError("each photo must be a record")
        tag = photo.get("tag")
        if not isinstance(tag, str) or tag == "":
            raise ValueError("tag must be a non-empty string")
        if tag in seen:
            raise ValueError(f"two photos answer to the tag {tag}")
        seen.add(tag)
        if not _whole(photo.get("wide"), 1) or not _whole(photo.get("high"), 1):
            raise ValueError("wide and high must be whole numbers above nought")
        span = (photo["wide"] * band) // photo["high"]
        if span == 0:
            raise ValueError(f"{tag} prints to nothing at this band height")
        if span > width:
            raise ValueError(f"{tag} is too wide to lie on a band by itself")
        if photo["high"] > photo["wide"]:
            family = "upright"
        elif photo["wide"] > photo["high"]:
            family = "oblong"
        else:
            family = "square"
        kept.append((tag, family, span))

    bands = []
    for family in FAMILIES:
        tags = []
        run = 0
        for tag, own, span in kept:
            if own != family:
                continue
            cost = span if not tags else gap + span
            if run + cost <= width:
                run += cost
                tags.append(tag)
            else:
                bands.append(
                    {"family": family, "tags": tags, "run": run, "spare": width - run}
                )
                tags = [tag]
                run = span
        if tags:
            bands.append(
                {"family": family, "tags": tags, "run": run, "spare": width - run}
            )
    return bands
