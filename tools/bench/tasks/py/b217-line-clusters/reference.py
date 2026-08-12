"""Group a tram operator's stops into the clusters its track segments join."""


def line_clusters(stops: list[str], links: list[tuple[str, str]]) -> list[list[str]]:
    home = {stop: stop for stop in stops}

    def root(stop: str) -> str:
        while home[stop] != stop:
            stop = home[stop]
        return stop

    for start, finish in links:
        home[root(start)] = root(finish)
    groups: dict[str, list[str]] = {}
    for stop in stops:
        groups.setdefault(root(stop), []).append(stop)
    clusters = [sorted(members) for members in groups.values()]
    clusters.sort(key=lambda cluster: cluster[0])
    return clusters
