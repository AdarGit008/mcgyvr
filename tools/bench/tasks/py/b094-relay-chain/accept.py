from solution import trace_relay

assert trace_relay({"depot": ""}, "depot") == ["depot"], "a terminal start walks itself"
assert trace_relay({"gate": "depot", "depot": ""}, "gate") == ["gate", "depot"], "one hand-off"
assert trace_relay({"gate": "depot", "depot": ""}, "depot") == [
    "depot"
], "starting mid-chain skips earlier stations"
assert trace_relay({"dock": "yard", "pier": "dock", "yard": "hub", "hub": ""}, "pier") == [
    "pier",
    "dock",
    "yard",
    "hub",
], "a long chain arrives in hand-off order"
assert trace_relay({"north": "hub", "south": "hub", "hub": ""}, "south") == [
    "south",
    "hub",
], "an unused branch stays out of the walk"
assert trace_relay({"north": "hub", "south": "hub", "hub": ""}, "north") == [
    "north",
    "hub",
], "each branch walks through the shared tail"


def rejects(links, start):
    try:
        trace_relay(links, start)
    except Exception:
        return True
    return False


assert rejects({"depot": ""}, "gate"), "an unknown start is rejected"
assert rejects({"depot": ""}, 42), "a non-string start is rejected"
assert rejects({"gate": "yard"}, "gate"), "a link to a missing station is rejected"
assert rejects({"gate": "depot", "depot": "gate"}, "gate"), "a two-station circle is rejected"
assert rejects({"loop": "loop"}, "loop"), "a station handing to itself is rejected"
assert rejects({"": "depot", "depot": ""}, "depot"), "an empty station name is rejected"
assert rejects({"gate": None, "depot": ""}, "depot"), "a non-string link is rejected"
print("ok")
