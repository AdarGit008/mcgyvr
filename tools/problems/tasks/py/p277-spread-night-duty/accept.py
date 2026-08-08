from solution import spread_night_duty

assert spread_night_duty(
    ["ivy", "hal", "gus"], [1, 1, 1, 1, 1, 1], [[], [], [], [], [], []]
) == ["gus", "hal", "ivy", "gus", "hal", "ivy"], "three sleepers take turns by name"
assert spread_night_duty(
    ["ann", "bea", "cal", "dot"],
    [2, 1, 1, 1, 2, 1, 1],
    [[], [], [], [], [], [], []],
) == [
    "ann",
    "bea",
    "cal",
    "dot",
    "bea",
    "cal",
    "dot",
], "the punishing nights steer who is lightest later"
assert spread_night_duty(["zoe", "amy"], [1, 1, 1, 1], [[], [], [], []]) == [
    "amy",
    "zoe",
    "?",
    "amy",
], "rest empties a night, and amy sorts before zoe"
assert spread_night_duty(["ann", "bea", "cal"], [1, 1, 1], [["ann"], [], ["bea"]]) == [
    "bea",
    "ann",
    "cal",
], "being away shifts the opening pick"
assert spread_night_duty(["ann", "bea", "cal"], [2, 2, 2], [[], [], []]) == [
    "ann",
    "bea",
    "cal",
], "three punishing nights, one each"
assert spread_night_duty(["sol"], [1, 1, 1, 1], [[], [], [], []]) == [
    "sol",
    "?",
    "?",
    "sol",
], "one person rests two nights between turns"
assert spread_night_duty(["ann", "bea"], [1, 1], [["ann", "bea"], []]) == [
    "?",
    "ann",
], "an unworked night rests nobody"


def rejects(crew, weights, away):
    try:
        spread_night_duty(crew, weights, away)
    except ValueError:
        return True
    return False


assert rejects([], [1], [[]]), "an empty crew is rejected"
assert rejects(["ann", "ann"], [1], [[]]), "a repeated crew name is rejected"
assert rejects(["ann", "?"], [1], [[]]), "the mark as a crew name is rejected"
assert rejects(["ann", 4], [1], [[]]), "a crew name that is not a string is rejected"
assert rejects(["ann"], [], []), "no nights at all is rejected"
assert rejects(["ann"], [3], [[]]), "a weight of three is rejected"
assert rejects(["ann"], [1, 1], [[]]), "away shorter than weights is rejected"
assert rejects(["ann"], [1], ["ann"]), "an away entry that is not a list is rejected"
assert rejects(["ann"], [1], [["eve"]]), "an away entry naming an outsider is rejected"
print("ok")
