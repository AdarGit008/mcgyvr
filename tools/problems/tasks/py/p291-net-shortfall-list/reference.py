def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def net_requirements(
    recipes: list[dict], stock: list[dict], target: str, batch: int
) -> list[dict]:
    if not isinstance(recipes, list):
        raise ValueError("recipes must be a list")
    if not isinstance(stock, list):
        raise ValueError("stock must be a list")
    if not isinstance(target, str) or not target:
        raise ValueError("target must be a non-empty string")
    if not _whole(batch) or batch < 1:
        raise ValueError("batch must be an integer of at least 1")

    index: dict[str, list] = {}
    for recipe in recipes:
        if not isinstance(recipe, dict):
            raise ValueError("a recipes entry must be a record")
        made = recipe.get("item")
        if not isinstance(made, str) or not made:
            raise ValueError("an item name must be a non-empty string")
        if made in index:
            raise ValueError(f"recipes gives the same item twice: {made}")
        needs = recipe.get("needs")
        if not isinstance(needs, list) or not needs:
            raise ValueError(f"needs must be a non-empty list: {made}")
        here: set[str] = set()
        for need in needs:
            if not isinstance(need, dict):
                raise ValueError("a needs entry must be a record")
            wanted = need.get("item")
            if not isinstance(wanted, str) or not wanted:
                raise ValueError("an item name must be a non-empty string")
            if wanted in here:
                raise ValueError(f"{made} names {wanted} twice")
            here.add(wanted)
            per = need.get("per")
            if not _whole(per) or per < 1:
                raise ValueError(f"per must be an integer of at least 1: {wanted}")
        index[made] = needs

    remaining: dict[str, int] = {}
    for shelf in stock:
        if not isinstance(shelf, dict):
            raise ValueError("a stock entry must be a record")
        name = shelf.get("item")
        if not isinstance(name, str) or not name:
            raise ValueError("an item name must be a non-empty string")
        if name in remaining:
            raise ValueError(f"stock gives the same item twice: {name}")
        held = shelf.get("held")
        if not _whole(held) or held < 0:
            raise ValueError(f"held must be an integer of at least 0: {name}")
        remaining[name] = held

    buy: dict[str, int] = {}
    chain: set[str] = set()

    def make(item: str, units: int) -> None:
        if item in chain:
            raise ValueError(f"the making loops through {item}")
        chain.add(item)
        for need in index[item]:
            call = units * need["per"]
            have = remaining.get(need["item"], 0)
            drawn = have if have < call else call
            remaining[need["item"]] = have - drawn
            standing = call - drawn
            if standing == 0:
                continue
            if need["item"] in index:
                make(need["item"], standing)
            else:
                buy[need["item"]] = buy.get(need["item"], 0) + standing
        chain.discard(item)

    if target in index:
        make(target, batch)
    else:
        buy[target] = batch

    return [{"item": name, "buy": buy[name]} for name in sorted(buy)]
