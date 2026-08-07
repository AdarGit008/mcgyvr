def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def fill_released_seats(
    seats: list[dict], waitlist: list[dict], releases: list[str]
) -> list[dict]:
    if (
        not isinstance(seats, list)
        or not isinstance(waitlist, list)
        or not isinstance(releases, list)
    ):
        raise ValueError("fill_released_seats expects three lists")

    band: dict[str, str] = {}
    holder: dict[str, str | None] = {}
    seated: set[str] = set()
    for row in seats:
        if not isinstance(row, dict):
            raise ValueError("every seat must be an object")
        if not all(isinstance(row.get(key), str) for key in ("seat", "holder", "band")):
            raise ValueError("a seat needs a seat id, a holder and a band")
        if row["seat"] in band:
            raise ValueError(f"two seats share the id {row['seat']}")
        if row["holder"] in seated:
            raise ValueError(f"{row['holder']} holds two seats")
        band[row["seat"]] = row["band"]
        holder[row["seat"]] = row["holder"]
        seated.add(row["holder"])

    runners: list[dict] = []
    ranks: set[int] = set()
    pairs: set[tuple[str, str]] = set()
    for row in waitlist:
        if not isinstance(row, dict):
            raise ValueError("every waitlist entry must be an object")
        if not isinstance(row.get("name"), str) or not isinstance(row.get("band"), str):
            raise ValueError("a waitlist entry needs a name and a band")
        if not _whole(row.get("years")) or row["years"] < 0:
            raise ValueError("years is a whole number, never negative")
        if not _whole(row.get("rank")):
            raise ValueError("rank is a whole number")
        if not isinstance(row.get("roving"), bool):
            raise ValueError("roving is a boolean")
        if row["rank"] in ranks:
            raise ValueError(f"two entries share the rank {row['rank']}")
        pair = (row["name"], row["band"])
        if pair in pairs:
            raise ValueError(f"{row['name']} waits twice on {row['band']}")
        ranks.add(row["rank"])
        pairs.add(pair)
        runners.append(
            {
                "name": row["name"],
                "band": row["band"],
                "years": row["years"],
                "rank": row["rank"],
                "roving": row["roving"],
                "standing": True,
            }
        )

    offers: list[dict] = []
    for name in releases:
        if not isinstance(name, str) or name not in band:
            raise ValueError(f"release names no seat: {name}")
        leaving = holder[name]
        if leaving is None:
            raise ValueError(f"seat already stands empty: {name}")
        holder[name] = None
        seated.discard(leaving)

        free = [one for one in runners if one["standing"] and one["name"] not in seated]
        wanted = band[name]
        field = [one for one in free if one["band"] == wanted]
        if not field:
            field = [one for one in free if one["roving"]]
        winner = None
        for one in field:
            if (
                winner is None
                or one["years"] > winner["years"]
                or (one["years"] == winner["years"] and one["rank"] < winner["rank"])
            ):
                winner = one
        if winner is None:
            offers.append({"seat": name, "taken": None})
            continue
        holder[name] = winner["name"]
        seated.add(winner["name"])
        for one in runners:
            if one["name"] == winner["name"]:
                one["standing"] = False
        offers.append({"seat": name, "taken": winner["name"]})
    return offers
