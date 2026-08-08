from solution import rank_series_net

BANDS = [
    {"limit": 4, "allowance": 0},
    {"limit": 9, "allowance": 3},
    {"limit": 19, "allowance": 8},
    {"limit": 28, "allowance": 15},
]


def leg(gross, weight):
    return {"gross": gross, "weight": weight}


def rejects(entries, bands):
    try:
        rank_series_net(entries, bands)
    except ValueError:
        return True
    return False


ADA = {"name": "Ada", "mark": 12, "rounds": [leg(90, 100), leg(88, 110), leg(95, 90)]}
BRY = {
    "name": "Bry",
    "mark": 2,
    "rounds": [leg(84, 100), leg(86, 100), leg(83, 100), leg(90, 100)],
}
CYD = {"name": "Cyd", "mark": 25, "rounds": [leg(100, 100), leg(98, 120), leg(102, 80)]}
DOV = {"name": "Dov", "mark": 5, "rounds": [leg(80, 100), leg(81, 100)]}
ELI = {"name": "Eli", "mark": 5, "rounds": []}

assert rank_series_net([ADA], BANDS) == {
    "standings": [{"place": 1, "name": "Ada", "total": 250, "counted": [0, 1, 2]}],
    "unranked": [],
}, "three rounds all count, and each weight is cut down on its own"

assert rank_series_net([BRY], BANDS) == {
    "standings": [{"place": 1, "name": "Bry", "total": 253, "counted": [0, 1, 2]}],
    "unranked": [],
}, "a fourth round sets the worst one aside"

assert rank_series_net([CYD], BANDS) == {
    "standings": [{"place": 1, "name": "Cyd", "total": 255, "counted": [0, 1, 2]}],
    "unranked": [],
}, "a weight above one hundred lifts the allowance"

assert rank_series_net([DOV, ADA, CYD, ELI, BRY], BANDS) == {
    "standings": [
        {"place": 1, "name": "Ada", "total": 250, "counted": [0, 1, 2]},
        {"place": 2, "name": "Bry", "total": 253, "counted": [0, 1, 2]},
        {"place": 3, "name": "Cyd", "total": 255, "counted": [0, 1, 2]},
    ],
    "unranked": ["Dov", "Eli"],
}, "short entries drop out and the rest are ordered by total"

assert rank_series_net(
    [
        {"name": "Fay", "mark": 0, "rounds": [leg(100, 100), leg(100, 100), leg(100, 100)]},
        {"name": "Gus", "mark": 0, "rounds": [leg(95, 100), leg(100, 100), leg(105, 100)]},
    ],
    BANDS,
) == {
    "standings": [
        {"place": 1, "name": "Gus", "total": 300, "counted": [0, 1, 2]},
        {"place": 2, "name": "Fay", "total": 300, "counted": [0, 1, 2]},
    ],
    "unranked": [],
}, "level totals are parted by the best remaining net"

assert rank_series_net(
    [
        {"name": "Ivo", "mark": 0, "rounds": [leg(100, 100), leg(100, 100), leg(100, 100)]},
        {"name": "Hal", "mark": 0, "rounds": [leg(100, 100), leg(100, 100), leg(100, 100)]},
    ],
    BANDS,
) == {
    "standings": [
        {"place": 1, "name": "Hal", "total": 300, "counted": [0, 1, 2]},
        {"place": 2, "name": "Ivo", "total": 300, "counted": [0, 1, 2]},
    ],
    "unranked": [],
}, "level on every count falls back to the name"

assert rank_series_net(
    [
        {
            "name": "Kip",
            "mark": 0,
            "rounds": [leg(90, 100), leg(95, 100), leg(95, 100), leg(80, 100)],
        }
    ],
    BANDS,
) == {
    "standings": [{"place": 1, "name": "Kip", "total": 265, "counted": [0, 1, 3]}],
    "unranked": [],
}, "two rounds level at the worst set the later one aside"

assert rank_series_net(
    [{"name": "Lys", "mark": 25, "rounds": [leg(100, 33), leg(100, 100), leg(100, 200)]}],
    BANDS,
) == {
    "standings": [{"place": 1, "name": "Lys", "total": 251, "counted": [0, 1, 2]}],
    "unranked": [],
}, "a weight of thirty three cuts fifteen down to four"

assert rank_series_net([ELI], BANDS) == {
    "standings": [],
    "unranked": ["Eli"],
}, "a competitor who played nothing stands nowhere"

assert rejects([], BANDS), "no entries is refused"
assert rejects("Ada", BANDS), "entries that are not a list are refused"
assert rejects([ADA], []), "no bands is refused"
assert rejects(
    [ADA], [{"limit": 9, "allowance": 3}, {"limit": 4, "allowance": 0}]
), "band limits that fall are refused"
assert rejects(
    [ADA], [{"limit": 4, "allowance": 0}, {"limit": 4, "allowance": 3}]
), "two bands sharing a limit are refused"
assert rejects(
    [{"name": "Ada", "mark": 30, "rounds": ADA["rounds"]}], BANDS
), "a mark above every band is refused"
assert rejects(
    [{"name": "", "mark": 2, "rounds": ADA["rounds"]}], BANDS
), "an empty name is refused"
assert rejects([ADA, ADA], BANDS), "one name entered twice is refused"
assert rejects(
    [{"name": "Ada", "mark": -1, "rounds": ADA["rounds"]}], BANDS
), "a negative mark is refused"
assert rejects(
    [{"name": "Ada", "mark": 2, "rounds": "three"}], BANDS
), "rounds that are not a list are refused"
assert rejects(
    [{"name": "Ada", "mark": 2, "rounds": [leg(0, 100)]}], BANDS
), "a gross score of zero is refused"
assert rejects(
    [{"name": "Ada", "mark": 2, "rounds": [leg(90, 0)]}], BANDS
), "a weight of zero is refused"
assert rejects(
    [{"name": "Ada", "mark": 2, "rounds": [leg(90, 201)]}], BANDS
), "a weight above two hundred is refused"
assert rejects([ADA], [{"limit": 4, "allowance": -1}]), "a negative band allowance is refused"
print("ok")
