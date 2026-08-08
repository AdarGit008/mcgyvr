from solution import stranded_ticker_pairs


def rejects(legs):
    try:
        stranded_ticker_pairs(legs)
    except ValueError:
        return True
    return False


assert stranded_ticker_pairs([["AAA", "BBB"]]) == [
    "BBB>AAA"
], "one leg leaves the return trip stranded"

assert stranded_ticker_pairs([["AAA", "BBB"], ["BBB", "AAA"]]) == [
], "a two-leg loop strands nothing"

assert stranded_ticker_pairs(
    [["AAA", "BBB"], ["BBB", "CCC"], ["CCC", "AAA"]]
) == [], "a three-leg loop reaches everything"

assert stranded_ticker_pairs([["AAA", "BBB"], ["BBB", "CCC"]]) == [
    "BBB>AAA",
    "CCC>AAA",
    "CCC>BBB",
], "a chain routes downstream only"

assert stranded_ticker_pairs([["CCC", "DDD"], ["AAA", "BBB"]]) == [
    "AAA>CCC",
    "AAA>DDD",
    "BBB>AAA",
    "BBB>CCC",
    "BBB>DDD",
    "CCC>AAA",
    "CCC>BBB",
    "DDD>AAA",
    "DDD>BBB",
    "DDD>CCC",
], "two islands strand every couple that crosses between them"

assert stranded_ticker_pairs(
    [["AAA", "HUB"], ["HUB", "AAA"], ["BBB", "HUB"], ["HUB", "BBB"]]
) == [], "a hub with legs both ways joins its spokes"

assert stranded_ticker_pairs([["AAA", "SSS"], ["BBB", "SSS"]]) == [
    "AAA>BBB",
    "BBB>AAA",
    "SSS>AAA",
    "SSS>BBB",
], "a ticker everyone buys into reaches nobody"

assert rejects([]), "no legs at all is rejected"
assert rejects([["AAA", "BBB", "CCC"]]), "a three-element leg is rejected"
assert rejects([["AAA", ""]]), "an empty ticker is rejected"
assert rejects([["AAA", 7]]), "a ticker that is not a string is rejected"
assert rejects([["AAA", "AAA"]]), "a leg on one ticker is rejected"
assert rejects([["AAA", "BBB"], ["AAA", "BBB"]]), "a leg published twice is rejected"

print("ok")
