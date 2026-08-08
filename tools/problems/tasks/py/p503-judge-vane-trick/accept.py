from solution import judge_vane_trick

assert judge_vane_trick(
    {
        "trump": "bare",
        "lead": 0,
        "holdings": [["5k", "2n"], ["9n", "4k"], ["7k"], ["3k", "8t"]],
        "played": ["5k", "9n", "7k", "3k"],
    }
) == {"taker": 2, "revokes": [1]}, "a hot card of an idle plume takes nothing"
assert judge_vane_trick(
    {
        "trump": "t",
        "lead": 2,
        "holdings": [["8p"], ["5p", "9k"], ["6p"], ["2t", "4p"]],
        "played": ["6p", "2t", "8p", "5p"],
    }
) == {"taker": 0, "revokes": [3]}, "a trump laid in renege is set aside"
assert judge_vane_trick(
    {
        "trump": "k",
        "lead": 0,
        "holdings": [["4n", "3t"], ["9t", "5k"], ["2k"], ["6n"]],
        "played": ["4n", "9t", "2k", "6n"],
    }
) == {"taker": 2, "revokes": []}, "the coolest trump still beats the hottest plain card"
assert judge_vane_trick(
    {
        "trump": "k",
        "lead": 0,
        "holdings": [["4n"], ["8k", "5n"], ["6n"], ["2n"]],
        "played": ["4n", "8k", "6n", "2n"],
    }
) == {"taker": 2, "revokes": [1]}, "the reneged trump is set aside"
assert judge_vane_trick(
    {
        "trump": "n",
        "lead": 1,
        "holdings": [["2p", "6t"], ["7t"], ["3n", "5t"], ["9t"]],
        "played": ["7t", "3n", "9t", "2p"],
    }
) == {"taker": 3, "revokes": [0, 2]}, "two seats renege and come out in order"
assert judge_vane_trick(
    {
        "trump": "bare",
        "lead": 3,
        "holdings": [["4p"], ["9p"], ["2p"], ["7p"]],
        "played": ["7p", "4p", "9p", "2p"],
    }
) == {"taker": 1, "revokes": []}, "one plume all round with the lead away from seat zero"

SOUND = {
    "trump": "bare",
    "lead": 0,
    "holdings": [["5k"], ["9n"], ["7k"], ["3k"]],
    "played": ["5k", "9n", "7k", "3k"],
}


def rejects(**changes):
    play = dict(SOUND)
    play.update(changes)
    try:
        judge_vane_trick(play)
    except ValueError:
        return True
    return False


def rejects_value(play):
    try:
        judge_vane_trick(play)
    except ValueError:
        return True
    return False


assert rejects_value("play"), "a string is not a play"
assert rejects(trump="z"), "an unknown trump plume"
assert rejects(lead=4), "a lead outside the table"
assert rejects(holdings=[["5k"], ["9n"], ["7k"]]), "three holdings are refused"
assert rejects(holdings=[["5k"], ["9n"], ["7k"], ["3k", "5k"]]), "one card in two holdings"
assert rejects(played=["5k", "9n", "7k"]), "three cards laid are refused"
assert rejects(played=["5k", "9n", "7k", "2t"]), "a card never held"
assert rejects(played=["5k", "9n", "7k", "10k"]), "a heat outside 2 to 9"
print("ok")
