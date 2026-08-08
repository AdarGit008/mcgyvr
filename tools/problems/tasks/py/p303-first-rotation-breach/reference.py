def first_rotation_breach(log: list[list[str]], permits: list[list[str]]) -> str:
    if not isinstance(log, list) or not log:
        raise ValueError("the record must be a non-empty list")
    seasons = -1
    for record in log:
        if not isinstance(record, list) or not record:
            raise ValueError("every plot row must be a non-empty list")
        if seasons == -1:
            seasons = len(record)
        elif len(record) != seasons:
            raise ValueError("plot rows run to unequal lengths")
        for crop in record:
            if not isinstance(crop, str) or not crop:
                raise ValueError("every recorded entry is a crop name")
    if not isinstance(permits, list):
        raise ValueError("the table must be a list")
    licensed = set()
    for row in permits:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("every table row is a pair")
        for crop in row:
            if not isinstance(crop, str) or not crop:
                raise ValueError("every table entry is a crop name")
        licensed.add((row[0], row[1]))

    for season in range(1, seasons):
        for plot, record in enumerate(log):
            crop = record[season]
            lifted = record[season - 1]
            breached = (lifted, crop) not in licensed
            if not breached and crop == lifted:
                breached = True
            if not breached and season >= 2 and crop == record[season - 2]:
                breached = True
            if breached:
                return f"plot {plot + 1} season {season + 1}"
    return "clear"
