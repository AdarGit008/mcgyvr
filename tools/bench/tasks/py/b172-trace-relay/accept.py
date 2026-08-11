from solution import trace_relay

night = {"gate": "dock", "dock": "yard", "yard": ""}
feeder = {"east": "hub", "west": "hub", "hub": ""}

assert trace_relay(night, "gate") == ["gate", "dock", "yard"], "the whole night is walked from the first post"
assert trace_relay(night, "dock") == ["dock", "yard"], "a start partway along walks only the rest"
assert trace_relay(night, "yard") == ["yard"], "the last post walks alone"
assert trace_relay({"solo": ""}, "solo") == ["solo"], "a one-post night is a one-name route"
assert trace_relay(feeder, "west") == ["west", "hub"], "two posts may hand on to the same post"
assert trace_relay(feeder, "east") == ["east", "hub"], "the other feeder post walks its own route"


def rejects(links, start):
    try:
        trace_relay(links, start)
    except ValueError:
        return True
    return False


assert rejects(["gate"], "gate"), "links that are not a mapping are rejected"
assert rejects(night, "roof"), "a start that is not a post is rejected"
assert rejects({"gate": "dock", "dock": "roof"}, "gate"), "a handoff to an unnamed post is rejected"
assert rejects({"bow": "stern", "stern": "bow"}, "bow"), "a watch that comes round again is rejected"
print("ok")
