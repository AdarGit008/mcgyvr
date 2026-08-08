def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def fold_signature_map(pages: int, per_signature: int, wanted: list) -> list:
    if not _whole(pages) or pages < 1 or pages > 20000:
        raise ValueError("the pages are not whole or fall outside one through twenty thousand")
    if not _whole(per_signature) or per_signature < 4 or per_signature > 400:
        raise ValueError(
            "the per_signature is not whole or falls outside four through four hundred"
        )
    if per_signature % 4 != 0:
        raise ValueError("the per_signature does not divide by four")
    if not isinstance(wanted, list):
        raise ValueError("the wanted pages are not a list")
    for page in wanted:
        if not _whole(page) or page < 1 or page > pages:
            raise ValueError(
                "a wanted page is not whole or falls outside one through the page count"
            )

    half = per_signature // 2
    lines = []
    for page in wanted:
        signature = (page - 1) // per_signature + 1
        place = page - (signature - 1) * per_signature
        if place % 2 == 1:
            if place <= half:
                sheet = (place + 1) // 2
                side = "front"
                edge = "right"
            else:
                sheet = (per_signature + 1 - place) // 2
                side = "back"
                edge = "right"
        elif place <= half:
            sheet = place // 2
            side = "back"
            edge = "left"
        else:
            sheet = (per_signature + 2 - place) // 2
            side = "front"
            edge = "left"
        lines.append(f"{page} {signature} {sheet} {side} {edge}")
    return lines
