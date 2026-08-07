def _is_whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def slice_repeating_band(motifs: list, strip_width: int, strip_count: int) -> list:
    if not isinstance(motifs, list):
        raise ValueError("the motifs are a list of lengths")
    if not motifs:
        raise ValueError("a run holds at least one motif")
    opens: list = []
    total = 0
    for length in motifs:
        if not _is_whole(length) or length < 1:
            raise ValueError("a motif length is a whole number of one or more")
        opens.append(total)
        total += length
    if not _is_whole(strip_width) or strip_width < 1 or strip_width > 1000:
        raise ValueError("strip_width is a whole number from 1 through 1000")
    if not _is_whole(strip_count) or strip_count < 0 or strip_count > 500:
        raise ValueError("strip_count is a whole number from 0 through 500")

    join_at = set(opens)
    cuts: list = []
    for strip in range(strip_count):
        left = strip * strip_width
        offset = left % total
        motif = 0
        for index, opening in enumerate(opens):
            if opening <= offset:
                motif = index
        joins = 0
        for at in range(left + 1, left + strip_width):
            if at % total in join_at:
                joins += 1
        cuts.append(
            {
                "motif": motif,
                "into": offset - opens[motif],
                "joins": joins,
                "runs": left // total,
            }
        )
    return cuts
