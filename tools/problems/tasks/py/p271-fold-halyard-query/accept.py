from solution import fold_halyard_query

assert fold_halyard_query("b=2&a=1") == "a=1&b=2", "parameters are put in name order"
assert fold_halyard_query("") == "", "an empty query folds to nothing"
assert fold_halyard_query("verbose&a=1") == "verbose&a=1", "a lone name comes ahead of a carrying one"
assert fold_halyard_query("z=1&mm") == "mm&z=1", "the lone name goes first even when it sorts later"
assert fold_halyard_query("one&two&three&k=v") == "one&three&two&k=v", "lone names sort among themselves"
assert fold_halyard_query("a=2&a=1&a=2") == "a=1,2", "a repeated name gathers its values and sheds the repeat"
assert fold_halyard_query("A=1&a=2") == "a=1,2", "names fold to lower case before gathering"
assert fold_halyard_query("_41=1") == "a=1", "a name written as an escape folds too"
assert fold_halyard_query("q=Zed&q=zed") == "q=Zed,zed", "values keep their case"
assert fold_halyard_query("Flag&flag") == "flag", "two spellings of one lone name become one"
assert fold_halyard_query("zeta&alpha") == "alpha&zeta", "lone names in rising order"
assert fold_halyard_query("x=&x=1") == "x=,1", "an empty value sorts ahead of the rest"
assert fold_halyard_query("n_5fm=1") == "n_5fm=1", "an underscore in a name survives the round trip"
assert fold_halyard_query("k=a_2cb") == "k=a_2cb", "a comma in a value survives the round trip"
assert fold_halyard_query("p=a_26b") == "p=a_26b", "an ampersand in a value survives the round trip"
assert fold_halyard_query("r=x_3dy") == "r=x_3dy", "an equals in a value survives the round trip"


def rejects(value):
    try:
        fold_halyard_query(value)
    except ValueError:
        return True
    return False


assert rejects("a&a=1"), "one name both standing alone and carrying"
assert rejects("=1"), "an empty name"
assert rejects("&"), "a bare separator"
assert rejects("a=1&"), "a trailing separator"
assert rejects("a=1=2"), "a second bare equals"
assert rejects("k=_2"), "an escape cut short"
assert rejects("k=_ZZ"), "an escape that is not hex"
assert rejects("k=_2C"), "an upper-case hex escape"
assert rejects("k=_20"), "an escape naming a space"
assert rejects("k=_7f"), "an escape above the visible band"
assert rejects("a b=1"), "a raw space in the query"
assert rejects(7), "a query that is not text"
print("ok")
