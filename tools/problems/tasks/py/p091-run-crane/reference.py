def run_crane(script):
    pile = []
    manifest = []
    for index, move in enumerate(script):
        name = move[0]
        if name == "load":
            pile.append(move[1])
        elif name == "ship":
            if not pile:
                raise ValueError(f"move {index}: pile is empty")
            manifest.append(pile.pop())
        elif name == "bury":
            if not pile:
                raise ValueError(f"move {index}: pile is empty")
            pile.insert(0, pile.pop())
        elif name == "scrap":
            if not pile:
                raise ValueError(f"move {index}: pile is empty")
            pile.pop()
        else:
            raise ValueError(f"move {index}: unknown move {name!r}")
    return manifest
