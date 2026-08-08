from solution import scale_batch_lines

assert scale_batch_lines(["200 g flour", "100 ml milk", "2 each egg"], 3, 2) == [
    "300 g flour",
    "150 ml milk",
    "3 each egg",
], "a clean ratio leaves every measure on its tick"
assert scale_batch_lines(["10 ml oil"], 1, 4) == [
    "5 ml oil"
], "a value halfway between ticks goes up"
assert scale_batch_lines(["1 g salt"], 1, 3) == [
    "1 g salt"
], "what settles to nothing becomes one tick"
assert scale_batch_lines(["100 g sugar"], 2, 3) == [
    "67 g sugar"
], "two thirds of a hundred settles upward"
assert scale_batch_lines(["7 ml vanilla extract"], 1, 1) == [
    "5 ml vanilla extract"
], "the ml tick binds even when the batch does not change"
assert scale_batch_lines(["3 ml tonic"], 1, 1) == [
    "5 ml tonic"
], "a small ml quantity is lifted to one tick"
assert scale_batch_lines([], 4, 1) == [], "an empty sheet stays empty"
assert scale_batch_lines(["3 each bay leaf", "40 g brown sugar"], 7, 3) == [
    "7 each bay leaf",
    "93 g brown sugar",
], "names of several words survive the rewrite"


def rejects(items, want, base):
    try:
        scale_batch_lines(items, want, base)
    except ValueError:
        return True
    return False


assert rejects("200 g flour", 1, 1), "a sheet that is not a list is rejected"
assert rejects([7], 1, 1), "a line that is not a string is rejected"
assert rejects(["200 flour"], 1, 1), "a two part line is rejected"
assert rejects(["0 g flour"], 1, 1), "a quantity of zero is rejected"
assert rejects(["01 g flour"], 1, 1), "a padded quantity is rejected"
assert rejects(["200 kg flour"], 1, 1), "an unknown measure is rejected"
assert rejects(["200 g flour2"], 1, 1), "a digit in the name is rejected"
assert rejects(["200 g  flour"], 1, 1), "a doubled space is rejected"
assert rejects(["1 g salt", "2 g salt"], 1, 1), "two lines naming the same stuff are rejected"
assert rejects(["1 g salt"], 0, 1), "a wanted count of zero is rejected"
assert rejects(["1 g salt"], 1, 0), "a written count of zero is rejected"
assert rejects(["1 g salt"], 1.5, 1), "a fractional portion count is rejected"
assert rejects(["1 g salt"], 1, "2"), "a portion count that is not a number is rejected"
print("ok")
