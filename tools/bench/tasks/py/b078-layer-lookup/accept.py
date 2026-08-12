from solution import config_value

assert config_value(["port=8080"], "port") == "8080", "a single layer supplies the value"
assert config_value(["port=8080\nhost=web", "port=9090"], "port") == "9090", "the later layer wins"
assert config_value(["mode=fast", "!mode"], "mode") is None, "a later unset hides the value"
assert config_value(["# port=off\n  host =  local  "], "host") == "local", "comments are skipped and whitespace is trimmed"
assert config_value(["flag="], "flag") == "", "an empty value is a value, not an unset"


def rejects(layers, name):
    try:
        config_value(layers, name)
    except Exception:
        return True
    return False


assert rejects(["port=8080"], 7), "non-string name is rejected"
assert rejects(["port=8080"], ""), "empty name is rejected"
assert rejects([42], "port"), "non-string layer is rejected"
assert rejects(["just a word"], "port"), "a line with no equals sign is rejected"
print("ok")
