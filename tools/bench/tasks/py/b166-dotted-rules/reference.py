def match_setting(rules, name):
    if not isinstance(name, str) or name == "" or "*" in name:
        raise ValueError("name must be a star-free non-empty string")
    exact, best, best_length = None, None, -1
    for selector, value in rules.items():
        if not isinstance(value, str):
            raise ValueError("every rule value must be a string")
        wildcard = selector == "*" or selector.endswith(".*")
        if "*" in selector and (not wildcard or selector.find("*") < len(selector) - 1):
            raise ValueError("a star may only stand alone or end a selector")
        if selector == name:
            exact = value
        if wildcard and name.startswith(selector[:-1]) and len(selector) > best_length:
            best, best_length = value, len(selector)
    return exact if exact is not None else best
