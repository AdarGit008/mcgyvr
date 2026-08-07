from solution import expand_glossary

assert expand_glossary(["1=red", "!1"]) == "red", "one store, one send"
assert expand_glossary([]) == "", "a script with no lines sends nothing"
assert (
    expand_glossary(["1=red", "2=big {1} ball", "!2"]) == "big red ball"
), "one splice inside a body"
assert (
    expand_glossary(["1=red", "2=big {1}", "3={2} ball", "!3"]) == "big red ball"
), "a body settled from a body that was itself settled"
assert (
    expand_glossary(["1={{x}}", "!1"]) == "{x}"
), "doubled braces are literal, not a splice"
assert expand_glossary(["1=ab", "!1", "!1"]) == "abab", "the same slot sent twice"
assert (
    expand_glossary(["1=a", "!1", "2=b", "!2"]) == "ab"
), "sends join in the order they appear"
assert (
    expand_glossary(["7=x", "12={7}{7}", "!12"]) == "xx"
), "multi-digit slot numbers and back-to-back splices"
assert (
    expand_glossary(["1=a", "2={1}}}", "!2"]) == "a}"
), "a doubled closing brace right after a splice"
assert expand_glossary(["1=", "2=[{1}]", "!2"]) == "[]", "an empty body splices"


def rejects(script):
    try:
        expand_glossary(script)
    except ValueError:
        return True
    return False


assert rejects(["1={2}", "2=x", "!1"]), "a splice naming a later slot"
assert rejects(["1=a", "1=b", "!1"]), "a slot stored twice"
assert rejects(["!1"]), "a send of a slot never stored"
assert rejects(["hello"]), "a line of neither kind"
assert rejects(["01=a", "!01"]), "a padded slot number"
assert rejects(["0=a", "!0"]), "a slot number of zero"
assert rejects(["1=a", "2={1", "!2"]), "a brace never closed"
assert rejects(["1=a}", "!1"]), "a closing brace with nothing open"
assert rejects("1=a"), "a script that is not a list"
print("ok")
