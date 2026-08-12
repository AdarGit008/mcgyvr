from solution import fill_template

assert fill_template("hi {who}", {"who": "crew"}) == "hi crew", "a placeholder is replaced"
assert fill_template("{p}{p}!", {"p": "go"}) == "gogo!", "adjacent and repeated placeholders"
assert fill_template("plain text", {}) == "plain text", "text without placeholders is unchanged"
assert fill_template("} {n} }", {"n": "q"}) == "} q }", "a closing brace outside a placeholder is literal"


def rejects(template, values):
    try:
        fill_template(template, values)
    except Exception:
        return True
    return False


assert rejects("tail {open", {}), "an unterminated placeholder is rejected"
assert rejects("{}", {}), "an empty name is rejected"
assert rejects("{a-b}", {}), "a bad character in a name is rejected"
assert rejects("{ghost}", {}), "an unknown name is rejected"
assert rejects(9, {}), "a non-string template is rejected"
print("ok")
