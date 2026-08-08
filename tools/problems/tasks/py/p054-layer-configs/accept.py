from solution import layer_configs

assert layer_configs([{"a": 1}, {"a": 2, "b": 3}]) == {
    "a": 2,
    "b": 3,
}, "later scalars override earlier ones"
assert layer_configs(
    [{"server": {"host": "x", "port": 1}}, {"server": {"port": 2}}]
) == {"server": {"host": "x", "port": 2}}, "nested mappings merge, preserving siblings"
assert layer_configs([{"a": 1, "b": 2}, {"a": None}]) == {
    "b": 2
}, "null deletes a key"
assert layer_configs([{"b": 1}, {"a": None}]) == {
    "b": 1
}, "deleting an absent key is silent"
assert layer_configs([{"tags": [1, 2]}, {"tags": [3]}]) == {
    "tags": [3]
}, "arrays replace wholesale, never concatenate"
assert layer_configs([{"a": {"x": 1}}, {"a": 5}]) == {
    "a": 5
}, "a scalar replaces a mapping wholesale"
assert layer_configs([{"a": 5}, {"a": {"x": 1}}]) == {
    "a": {"x": 1}
}, "a mapping replaces a scalar wholesale"
assert layer_configs([{"a": {"x": 1, "y": 2}}, {"a": {"x": None}}]) == {
    "a": {"y": 2}
}, "null deletes inside a nested merge"
assert layer_configs([{"a": 1}, {"a": None}, {"a": {"x": 2}}]) == {
    "a": {"x": 2}
}, "a deleted key may be reintroduced later"
assert layer_configs([]) == {}, "no layers yield an empty result"

pristine = {"server": {"port": 1}}
layer_configs([pristine, {"server": {"port": 9}}])
assert pristine == {"server": {"port": 1}}, "layers must not be mutated"


def rejects(layers):
    try:
        layer_configs(layers)
    except ValueError:
        return True
    return False


assert rejects("nope"), "non-list argument rejected"
assert rejects([[1, 2]]), "array layer rejected"
assert rejects([None]), "null layer rejected"
print("ok")
