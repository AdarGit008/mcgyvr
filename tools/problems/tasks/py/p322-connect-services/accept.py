from solution import connect_services

base = [
    {"code": "S1", "from": "A", "to": "B", "depart": 500, "arrive": 530},
    {"code": "S2", "from": "B", "to": "C", "depart": 545, "arrive": 600},
    {"code": "S3", "from": "A", "to": "C", "depart": 505, "arrive": 650},
    {"code": "S4", "from": "B", "to": "C", "depart": 535, "arrive": 555},
    {"code": "S5", "from": "C", "to": "D", "depart": 610, "arrive": 640},
]

assert connect_services(base, "A", "C", 0, 10) == {
    "arrive": 600,
    "legs": ["S1", "S2"],
}, "the tight change at 535 is unreachable with a ten minute minimum"
assert connect_services(base, "A", "C", 0, 0) == {
    "arrive": 555,
    "legs": ["S1", "S4"],
}, "with no minimum the tight change wins"
assert connect_services(base, "A", "C", 502, 10) == {
    "arrive": 650,
    "legs": ["S3"],
}, "ready_at rules out the 500 departure"
assert connect_services(base, "A", "D", 0, 10) == {
    "arrive": 640,
    "legs": ["S1", "S2", "S5"],
}, "a three service journey"
assert connect_services(base, "A", "D", 0, 0) == {
    "arrive": 640,
    "legs": ["S1", "S2", "S5"],
}, "equal arrivals and equal leg counts fall to the codes"
assert connect_services(base, "D", "A", 0, 10) == {
    "arrive": -1,
    "legs": [],
}, "nothing runs back from D"
assert connect_services(base, "A", "C", 700, 10) == {
    "arrive": -1,
    "legs": [],
}, "arriving after the last departure strands the traveller"
assert connect_services([], "A", "C", 0, 0) == {
    "arrive": -1,
    "legs": [],
}, "an empty timetable connects nothing"

tied = [
    {"code": "S1", "from": "A", "to": "B", "depart": 500, "arrive": 530},
    {"code": "S2", "from": "B", "to": "C", "depart": 545, "arrive": 600},
    {"code": "M9", "from": "B", "to": "C", "depart": 545, "arrive": 600},
]
assert connect_services(tied, "A", "C", 0, 10) == {
    "arrive": 600,
    "legs": ["S1", "M9"],
}, "identical second legs are decided by the code"

short = [
    {"code": "D1", "from": "X", "to": "Y", "depart": 100, "arrive": 200},
    {"code": "E1", "from": "X", "to": "Z", "depart": 100, "arrive": 140},
    {"code": "E2", "from": "Z", "to": "Y", "depart": 150, "arrive": 200},
]
assert connect_services(short, "X", "Y", 0, 5) == {
    "arrive": 200,
    "legs": ["D1"],
}, "a shared arrival prefers the journey with fewer services"

looped = [
    {"code": "L1", "from": "P", "to": "Q", "depart": 10, "arrive": 20},
    {"code": "L2", "from": "Q", "to": "P", "depart": 30, "arrive": 40},
    {"code": "L3", "from": "P", "to": "R", "depart": 50, "arrive": 60},
]
assert connect_services(looped, "P", "R", 0, 0) == {
    "arrive": 60,
    "legs": ["L3"],
}, "a timetable that loops back does not trap the search"


def rejects(*args):
    try:
        connect_services(*args)
    except ValueError:
        return True
    return False


assert rejects("timetable", "A", "C", 0, 0), "the timetable must be a list"
assert rejects(
    [{"code": "Z", "from": "A", "to": "B", "depart": 1}], "A", "B", 0, 0
), "a service missing arrive is rejected"
assert rejects(
    [
        {"code": "Z", "from": "A", "to": "B", "depart": 1, "arrive": 2},
        {"code": "Z", "from": "B", "to": "C", "depart": 3, "arrive": 4},
    ],
    "A",
    "C",
    0,
    0,
), "two services sharing a code are rejected"
assert rejects(
    [{"code": "Z", "from": "A", "to": "B", "depart": 9, "arrive": 9}], "A", "B", 0, 0
), "an arrival not later than the departure is rejected"
assert rejects(
    [{"code": "Z", "from": "A", "to": "A", "depart": 1, "arrive": 2}], "A", "B", 0, 0
), "a service that sets down where it picked up is rejected"
assert rejects(base, "A", "C", 0, -1), "a negative min_transfer is rejected"
assert rejects(base, "A", "C", "soon", 0), "a non-numeric ready_at is rejected"
assert rejects(base, "A", "A", 0, 0), "origin equal to destination is rejected"
assert rejects(base, 42, "C", 0, 0), "a non-string origin is rejected"
assert rejects(base, "A", "", 0, 0), "an empty destination is rejected"
print("ok")
