import math


def explode_kit(catalog, kit, want):
    """Total the base parts an order of a kit consumes."""
    if kit not in catalog:
        raise ValueError(f"the catalog does not define {kit}")
    totals = {}

    def order(name, units):
        recipe = catalog[name]
        runs = math.ceil(units / recipe["makes"])
        for component, count in recipe["parts"]:
            needed = runs * count
            if component in catalog:
                order(component, needed)
            else:
                totals[component] = totals.get(component, 0) + needed

    order(kit, want)
    return totals
