"""Evaluate a mass tally written with unit-suffixed terms."""

import re

GRAMS = {"g": 1, "kg": 1000, "t": 1000000}
TERM = re.compile(r"^(0|[1-9][0-9]*)(g|kg|t)$")


def mass_expression(text, unit):
    if not isinstance(text, str) or text == "":
        raise ValueError("the tally must be a non-empty string")
    if unit not in GRAMS:
        raise ValueError("the goal unit must be g, kg or t")

    def term_grams(token):
        match = TERM.match(token)
        if match is None:
            raise ValueError("a term is a whole count directly on its unit")
        return int(match.group(1)) * GRAMS[match.group(2)]

    tokens = text.split(" ")
    if len(tokens) % 2 == 0:
        raise ValueError("terms and operators must alternate, ending on a term")
    grams = term_grams(tokens[0])
    for i in range(1, len(tokens), 2):
        op = tokens[i]
        value = term_grams(tokens[i + 1])
        if op == "+":
            grams += value
        elif op == "-":
            grams -= value
        else:
            raise ValueError("operators are + and -")
        if grams < 0:
            raise ValueError("the tally must never dip below zero")
    if grams % GRAMS[unit] != 0:
        raise ValueError("the total must come out whole in the goal unit")
    return grams // GRAMS[unit]
