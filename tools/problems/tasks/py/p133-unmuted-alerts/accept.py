from solution import unmuted_alerts


def alert(ident, resource, severity):
    return {"id": ident, "resource": resource, "severity": severity}


assert unmuted_alerts([alert("db1", "db", 2), alert("web1", "web", 5)]) == [
    "web1",
    "db1",
], "muting is per resource, so the quieter resource still shows its alert"
assert unmuted_alerts([alert("low", "db", 2), alert("high", "db", 4)]) == [
    "high"
], "a strictly higher severity on the same resource mutes the lower one"
assert unmuted_alerts([alert("b", "db", 3), alert("a", "db", 3)]) == [
    "a",
    "b",
], "equal severities never mute each other and tie-break by id"
assert unmuted_alerts([alert("a", "r1", 2), alert("z", "r2", 9)]) == [
    "z",
    "a",
], "the shortlist orders by severity descending, not by id"
assert unmuted_alerts(
    [alert("m", "r1", 1), alert("n", "r1", 7), alert("p", "r2", 7), alert("q", "r3", 4)]
) == ["n", "p", "q"], "three resources keep their own winners, ties by id"
assert unmuted_alerts([]) == [], "no alerts yields an empty shortlist"
assert unmuted_alerts([alert("solo", "cache", 1)]) == [
    "solo"
], "a lone alert is never muted"


def rejects(alerts):
    try:
        unmuted_alerts(alerts)
    except ValueError:
        return True
    return False


assert rejects(
    [alert("dup", "db", 2), alert("dup", "web", 3)]
), "a shared id is rejected"
assert rejects([alert("x", "db", 0)]), "severity 0 is rejected"
assert rejects([alert("x", "db", 2.5)]), "a fractional severity is rejected"
print("ok")
