from solution import count_sentences


def rejects(*args):
    try:
        count_sentences(*args)
    except ValueError:
        return True
    return False


assert count_sentences("It rained. It stopped.", []) == 2, "two endings"
assert count_sentences("Dr. Vance paid. Nobody argued.", ["Dr"]) == 2, (
    "a supplied title makes the stop inert"
)
assert count_sentences("Dr. Vance paid. Nobody argued.", []) == 3, (
    "with no titles the same stop ends a sentence"
)
assert count_sentences("Dr. Vance paid. Nobody argued.", ["dr"]) == 3, (
    "titles are compared with case respected"
)
assert count_sentences("The dial read 12.5 today.", []) == 1, (
    "a stop between digits is inert"
)
assert count_sentences("Ask J. Vance first.", []) == 1, (
    "a single capital before the stop marks an initial"
)
assert count_sentences("Check [the note. it helps] now. Go.", []) == 2, (
    "square brackets shelter their stops"
)
assert count_sentences("She said 'Wait. Stop.' then left.", []) == 1, (
    "an aside shelters its stops"
)
assert count_sentences("Really?! Truly.", []) == 2, "a run ends one sentence"
assert count_sentences("Bang! No stop at the end", []) == 2, (
    "a trailing fragment counts as one more"
)
assert count_sentences("Trailing words", []) == 1, "no marks at all"
assert count_sentences("", []) == 0, "empty prose"
assert count_sentences("     ", []) == 0, "only spaces"

assert rejects(7, []), "prose must be a string"
assert rejects("Hi.", "Dr"), "titles must be a list"
assert rejects("Hi.", [""]), "an empty title"
assert rejects("Hi.", ["Dr."]), "a title with a stop"
assert rejects("Hi] there.", []), "closed with no opener"
assert rejects("Hi [there.", []), "left open"
assert rejects("Hi 'there.", []), "aside left open"
print("ok")
