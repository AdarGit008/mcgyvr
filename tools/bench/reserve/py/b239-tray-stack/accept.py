from solution import tray_push, tray_top

held = ["a"]
assert tray_push([], "a") == ["a"], "the first item"
assert tray_push(held, "b") == ["a", "b"], "the new item rests on top"
assert held == ["a"], "the original stack is untouched"
assert tray_top(["a", "b"]) == "b", "the top is the last pushed"
assert tray_top(["z"]) == "z", "a lone item is the top"
assert tray_top([]) is None, "an empty stack has no top"
print("ok")
