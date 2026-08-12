def menu_pick(dishes: list, budget: int) -> list:
    affordable = []
    for dish in dishes:
        if dish["price"] <= budget:
            affordable.append(dish)
    affordable.sort(key=lambda dish: (dish["price"], dish["name"]))
    return [dish["name"] for dish in affordable]
