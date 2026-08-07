def league_order(matches):
    if not isinstance(matches, list):
        raise ValueError("matches must be a list")
    table = {}
    games = []

    def side(team):
        if team not in table:
            table[team] = {"pts": 0, "gd": 0, "gf": 0}
        return table[team]

    for entry in matches:
        if not isinstance(entry, list) or len(entry) != 4:
            raise ValueError("each match is a 4-item list")
        a, b, ga, gb = entry
        if not isinstance(a, str) or not isinstance(b, str):
            raise ValueError("team names must be strings")
        if a == b:
            raise ValueError("a team cannot face itself")
        for goals in (ga, gb):
            if isinstance(goals, bool) or not isinstance(goals, int) or goals < 0:
                raise ValueError("goals must be non-negative integers")
        games.append((a, b, ga, gb))
        home, away = side(a), side(b)
        home["pts"] += 3 if ga > gb else (1 if ga == gb else 0)
        away["pts"] += 3 if gb > ga else (1 if ga == gb else 0)
        home["gd"] += ga - gb
        away["gd"] += gb - ga
        home["gf"] += ga
        away["gf"] += gb

    standings = []
    for pts in sorted({row["pts"] for row in table.values()}, reverse=True):
        group = [team for team in table if table[team]["pts"] == pts]
        mini = {team: 0 for team in group}
        for a, b, ga, gb in games:
            if a in mini and b in mini:
                mini[a] += 3 if ga > gb else (1 if ga == gb else 0)
                mini[b] += 3 if gb > ga else (1 if ga == gb else 0)
        group.sort(
            key=lambda team: (
                -mini[team],
                -table[team]["gd"],
                -table[team]["gf"],
                team,
            )
        )
        standings.extend(group)
    return standings
