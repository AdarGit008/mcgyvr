from solution import space_artist_run


def track(title, artist):
    return {"title": title, "artist": artist}


def rejects(value):
    try:
        space_artist_run(value)
    except ValueError:
        return True
    return False


assert space_artist_run([track("solo", "Vela")]) == ["solo"], "one track is its own run"

assert space_artist_run(
    [track("a1", "Vela"), track("a2", "Vela"), track("b1", "Kesh")]
) == ["a1", "b1", "a2"], "the busier artist opens and closes"

assert space_artist_run([track("t1", "Pell"), track("t2", "Quire")]) == [
    "t1",
    "t2",
], "level artists go by which appeared first"

assert space_artist_run(
    [
        track("x1", "Vela"),
        track("x2", "Vela"),
        track("x3", "Vela"),
        track("y1", "Kesh"),
        track("y2", "Kesh"),
        track("z1", "Orn"),
    ]
) == ["x1", "y1", "x2", "y2", "x3", "z1"], "six tracks over three artists"

assert space_artist_run(
    [track("x1", "Vela"), track("x2", "Vela"), track("y1", "Kesh"), track("z1", "Orn")]
) == ["x1", "y1", "x2", "z1"], "a level pair is settled by first appearance"

assert space_artist_run(
    [
        track("a1", "Pell"),
        track("a2", "Pell"),
        track("b1", "Quire"),
        track("b2", "Quire"),
        track("b3", "Quire"),
    ]
) == ["b1", "a1", "b2", "a2", "b3"], "the run need not open with the first track handed over"

assert space_artist_run(
    [
        track("m1", "Orn"),
        track("m2", "Vela"),
        track("m3", "Orn"),
        track("m4", "Vela"),
    ]
) == ["m1", "m2", "m3", "m4"], "two artists of equal weight alternate in order"

assert rejects([]), "an empty list is refused"
assert rejects("tracks"), "a non-list is refused"
assert rejects([track("a1", "Vela"), track("a2", "Vela")]), "two tracks by one artist cannot be parted"
assert rejects(
    [track("a1", "Vela"), track("a2", "Vela"), track("a3", "Vela"), track("b1", "Kesh")]
), "an artist holding more than half the run is refused"
assert rejects([track("", "Vela"), track("b1", "Kesh")]), "an empty title is refused"
assert rejects([{"title": "a1"}, track("b1", "Kesh")]), "a missing artist is refused"
assert rejects([track("same", "Vela"), track("same", "Kesh")]), "two tracks sharing a title are refused"
assert rejects([track("a1", 7), track("b1", "Kesh")]), "an artist that is not a string is refused"
print("ok")
