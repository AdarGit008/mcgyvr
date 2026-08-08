from solution import veil_encode

assert veil_encode("march", "bad cab") == "amc rma", "worked example"
assert veil_encode("crystal", "the mixer hums") == "izt qxetk zhqj", "longer keyword"
assert veil_encode("z", "az za") == "za az", "single-letter keyword swaps ends"
assert veil_encode("quartz", "pack my box") == "lqas oc umd", "mid-alphabet keyword"
assert veil_encode("banana", "abn") == "bap", "keyword repeats are skipped"
assert veil_encode("veil", "veil code") == "fzur iolz", "keyword letters map first"
assert veil_encode("march", "") == "", "empty message encodes to empty"


def rejects(keyword, message):
    try:
        veil_encode(keyword, message)
    except ValueError:
        return True
    return False


assert rejects("", "hi"), "empty keyword is rejected"
assert rejects("Big", "hi"), "uppercase keyword is rejected"
assert rejects("k1", "hi"), "digit in keyword is rejected"
assert rejects("key", "Hi"), "uppercase message is rejected"
assert rejects("key", 5), "non-string message is rejected"
print("ok")
