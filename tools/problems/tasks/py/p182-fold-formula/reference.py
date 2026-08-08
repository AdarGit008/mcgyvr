def fold_formula(recipe: str) -> str:
    if not isinstance(recipe, str):
        raise ValueError("recipe must be a string")
    if len(recipe) == 0:
        raise ValueError("empty recipe")

    at = 0

    def read_repeat():
        nonlocal at
        if at >= len(recipe) or not recipe[at].isdigit():
            return 1
        if recipe[at] == "0":
            raise ValueError("repeat begins with a zero")
        digits = ""
        while at < len(recipe) and recipe[at].isdigit():
            digits += recipe[at]
            at += 1
        return int(digits)

    def read_recipe():
        nonlocal at
        tally = {}
        items = 0
        while at < len(recipe) and recipe[at] != ")":
            if recipe[at] == "(":
                at += 1
                body = read_recipe()
                if at >= len(recipe) or recipe[at] != ")":
                    raise ValueError("parenthesis left open")
                at += 1
            else:
                head = recipe[at]
                if not ("A" <= head <= "Z"):
                    raise ValueError("item does not start with an uppercase letter")
                at += 1
                tag = head
                while at < len(recipe) and "a" <= recipe[at] <= "z":
                    if len(tag) == 3:
                        raise ValueError("tag carries three lowercase letters")
                    tag += recipe[at]
                    at += 1
                body = {tag: 1}
            repeat = read_repeat()
            for name, count in body.items():
                tally[name] = tally.get(name, 0) + count * repeat
            items += 1
        if items == 0:
            raise ValueError("parentheses enclose nothing")
        return tally

    totals = read_recipe()
    if at != len(recipe):
        raise ValueError("closing parenthesis with no opener")
    return "".join(
        tag if totals[tag] == 1 else tag + str(totals[tag]) for tag in sorted(totals)
    )
