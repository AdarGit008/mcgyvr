from solution import rebuild_from_last_column

assert rebuild_from_last_column("nnbaaa", 3) == "banana", "the stated banana column"
assert (
    rebuild_from_last_column("pssmipissii", 4) == "mississippi"
), "a column thick with repeats"
assert (
    rebuild_from_last_column("rdarcaaaabb", 2) == "abracadabra"
), "five a letters must keep their pairing"
assert rebuild_from_last_column("vllee", 2) == "level", "a short repeat"
assert rebuild_from_last_column("eeffoc", 0) == "coffee", "home at seat zero"
assert rebuild_from_last_column("a", 0) == "a", "a lone letter"
assert rebuild_from_last_column("dabc", 0) == "abcd", "all letters different"
assert rebuild_from_last_column("mottoa", 4) == "tomato", "home near the end"


def rejects(column, home):
    try:
        rebuild_from_last_column(column, home)
    except ValueError:
        return True
    return False


assert rejects(9, 0), "a column that is not a string is thrown out"
assert rejects("", 0), "an empty column is thrown out"
assert rejects("ba7a", 1), "a column outside a to z is thrown out"
assert rejects("abc", "1"), "a home that is not a whole number is thrown out"
assert rejects("abc", 3), "a home past the column is thrown out"
assert rejects("abc", -1), "a home below zero is thrown out"
print("ok")
