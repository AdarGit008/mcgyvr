from solution import broadcast_waves


def rejects(links, start):
    try:
        broadcast_waves(links, start)
    except ValueError:
        return True
    return False


assert broadcast_waves(["a>b", "b>c"], "a") == "a\nb\nc", "a plain chain gives one desk per wave"
assert broadcast_waves(["a>c", "a>b"], "a") == "a\nb, c", "a wave lists its desks alphabetically"
assert broadcast_waves(["a>b", "a>c", "b>d", "c>d"], "a") == "a\nb, c\nd", "a desk joins only its earliest wave"
assert broadcast_waves([], "desk") == "desk", "a start with no links is a single wave"
assert broadcast_waves(["a>b", "x>y"], "a") == "a\nb", "desks the bulletin never reaches are left out"
assert broadcast_waves(["a>b", "b>a"], "a") == "a\nb", "a link back to the start ends the spread"
assert rejects(["a-b"], "a"), "a link without sender>receiver is rejected"
print("ok")
