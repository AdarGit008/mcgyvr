def course_weight_total(categories: list) -> int:
    if not isinstance(categories, list) or not categories:
        raise ValueError("the syllabus holds no categories")
    labels = set()
    weights = 0
    answer = 0
    for category in categories:
        if not isinstance(category, dict):
            raise ValueError("a category must be a mapping")
        label = category.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError("a category needs a non-empty label")
        if label in labels:
            raise ValueError("duplicate category label: " + label)
        labels.add(label)
        weight = category.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight < 0:
            raise ValueError("weight must be a non-negative whole number")
        weights += weight
        items = category.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("category " + label + " holds no items")
        earned = 0
        worth = 0
        for item in items:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError("an item is a pair of whole numbers")
            got, possible = item
            for number in (got, possible):
                if not isinstance(number, int) or isinstance(number, bool):
                    raise ValueError("item points must be whole numbers")
            if possible <= 0:
                raise ValueError("an item must be worth something")
            if got < 0 or got > possible:
                raise ValueError("earned points fall outside the item's worth")
            earned += got
            worth += possible
        answer += (weight * earned) // worth
    if weights != 10000:
        raise ValueError("weights add up to " + str(weights) + ", not 10000")
    return answer
