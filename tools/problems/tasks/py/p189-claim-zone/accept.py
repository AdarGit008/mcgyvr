from solution import claim_zone

nest = ["0.0.0/0 world", "5.0.0/1 wing", "5.9.0/2 aisle", "5.9.15/3 slot"]

assert claim_zone([], "1.2.3") == "", "no claims covers nothing"
assert claim_zone(["0.0.0/0 world"], "5.9.15") == "world", "depth zero covers all"
assert claim_zone(nest, "5.9.15") == "slot", "the deepest stencil wins"
assert claim_zone(list(reversed(nest)), "5.9.15") == "slot", "arrival order does not matter"
assert claim_zone(nest, "5.9.14") == "aisle", "one number off drops a depth"
assert claim_zone(nest, "5.10.0") == "wing", "two numbers off drops two depths"
assert claim_zone(nest, "6.0.0") == "world", "only the widest stencil is left"
assert claim_zone(nest[1:], "6.0.0") == "", "nothing covers it at all"
assert claim_zone(["12.0.0/1 far"], "12.15.15") == "far", "two-digit numbers"
assert claim_zone(["0.0.0/3 origin"], "0.0.0") == "origin", "the origin post"


def rejects(claims, where="1.2.3"):
    try:
        claim_zone(claims, where)
    except ValueError:
        return True
    return False


assert rejects(["1.0.0/1 a", "1.0.0/1 b"]), "a repeated stencil is rejected"
assert rejects(["1.2.3/4 a"]), "depth four is rejected"
assert rejects(["1.2.3/1 a"]), "a live number after the fixed ones is rejected"
assert rejects(["1.2/2 a"]), "two numbers are rejected"
assert rejects(["1.2.16/3 a"]), "sixteen is rejected"
assert rejects(["01.2.3/3 a"]), "a padded number is rejected"
assert rejects(["1.0.0/1"]), "a nameless claim is rejected"
assert rejects(["1.0.0/1 "]), "an empty name is rejected"
assert rejects(["1.0.0/1 a b"]), "a spaced name is rejected"
assert rejects(["1.0.0-1 a"]), "a slashless stencil is rejected"
assert rejects(nest, "1.2"), "a short where is rejected"
assert rejects("0.0.0/0 world"), "a bare string is rejected"
assert rejects([5]), "a non-string claim is rejected"
print("ok")
