def runoff_winner(ballots: list) -> str:
    if not isinstance(ballots, list) or not ballots:
        raise ValueError("there must be at least one ballot")
    papers = []
    for ballot in ballots:
        if not isinstance(ballot, list) or not ballot:
            raise ValueError("a ballot must be a non-empty list")
        seen = set()
        for name in ballot:
            if not isinstance(name, str) or name == "":
                raise ValueError("an option must be a non-empty string")
            if name in seen:
                raise ValueError("a ballot names one option twice")
            seen.add(name)
        papers.append(list(ballot))

    standing = []
    for ballot in papers:
        for name in ballot:
            if name not in standing:
                standing.append(name)

    while True:
        tally = {name: 0 for name in standing}
        counted = 0
        for ballot in papers:
            top = next((name for name in ballot if name in tally), None)
            if top is not None:
                tally[top] += 1
                counted += 1
        for name, votes in tally.items():
            if votes * 2 > counted:
                return name
        if len(standing) == 1:
            return standing[0]
        doomed = None
        fewest = None
        for name, votes in tally.items():
            if fewest is None or votes < fewest or (votes == fewest and name > doomed):
                fewest = votes
                doomed = name
        standing.remove(doomed)
