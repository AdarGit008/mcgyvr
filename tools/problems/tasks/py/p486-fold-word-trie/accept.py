from solution import fold_word_trie

assert (
    fold_word_trie(["ant", "ante", "anvil", "bee"]) == "an(t(-|e)|vil)|bee"
), "the worked example squeezes as stated"
assert (
    fold_word_trie(["car", "card", "care", "cat"]) == "ca(r(-|d|e)|t)"
), "the second worked example squeezes as stated"
assert fold_word_trie(["a"]) == "a", "one word squeezes to itself"
assert fold_word_trie(["quill"]) == "quill", "a long lone word keeps its letters"
assert (
    fold_word_trie(["z", "b", "a"]) == "a|b|z"
), "runs come out in rising order whatever order they arrived in"
assert (
    fold_word_trie(["a", "ab"]) == "a(-|b)"
), "a word that is the whole opening becomes a dash"
assert fold_word_trie(["ac", "ab"]) == "a(b|c)", "two tails need no dash"
assert (
    fold_word_trie(["dust", "dog", "do", "doze", "dot"]) == "d(o(-|g|t|ze)|ust)"
), "the recipe applies again inside a bracket"
assert (
    fold_word_trie(["ox", "oxen", "oxide", "pea", "peat", "pear"])
    == "ox(-|en|ide)|pea(-|r|t)"
), "two runs each carry their own dash"
assert (
    fold_word_trie(["mist", "mister", "mistle", "misty"]) == "mist(-|er|le|y)"
), "a shared opening may run the whole length of a word"


def rejects(words):
    try:
        fold_word_trie(words)
    except ValueError:
        return True
    return False


assert rejects("ant"), "words must be a list"
assert rejects([]), "an empty list is rejected"
assert rejects(["ant", 5]), "a word must be a string"
assert rejects(["ant", ""]), "an empty word is rejected"
assert rejects(["Ant"]), "a capital letter is rejected"
assert rejects(["an-t"]), "a dash inside a word is rejected"
assert rejects(["ant", "ant"]), "a repeated word is rejected"
print("ok")
