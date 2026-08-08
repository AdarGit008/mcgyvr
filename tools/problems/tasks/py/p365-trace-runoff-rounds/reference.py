def trace_runoff_rounds(papers: list) -> list:
    if not isinstance(papers, list) or not papers:
        raise ValueError("there must be at least one paper")
    sheets = []
    met = []
    for paper in papers:
        if not isinstance(paper, list) or not paper:
            raise ValueError("a paper must be a non-empty list")
        seen = set()
        for name in paper:
            if not isinstance(name, str) or name == "":
                raise ValueError("a runner must be a non-empty string")
            if "|" in name or "," in name or "=" in name:
                raise ValueError("a runner name may not hold a bar, comma or equals")
            if name in seen:
                raise ValueError("a paper names one runner twice")
            seen.add(name)
            if name not in met:
                met.append(name)
        sheets.append(list(paper))

    standing = list(met)
    prior = None
    lines = []
    round_number = 1

    while True:
        tally = {name: 0 for name in standing}
        handed = 0
        for sheet in sheets:
            top = next((name for name in sheet if name in tally), None)
            if top is not None:
                tally[top] += 1
                handed += 1
        shown = sorted(standing, key=lambda name: (-tally[name], met.index(name)))
        body = ",".join(f"{name}={tally[name]}" for name in shown)

        winner = next((name for name in standing if tally[name] * 2 > handed), None)
        if winner is not None or len(standing) == 1:
            lines.append(f"{round_number}|{body}|won:{winner or standing[0]}")
            return lines

        fewest = min(tally[name] for name in standing)
        doomed_set = [name for name in standing if tally[name] == fewest]
        if len(doomed_set) > 1 and prior is not None:
            lowest = min(prior[name] for name in doomed_set)
            doomed_set = [name for name in doomed_set if prior[name] == lowest]
        doomed = max(doomed_set, key=met.index)
        lines.append(f"{round_number}|{body}|out:{doomed}")
        standing = [name for name in standing if name != doomed]
        prior = tally
        round_number += 1
