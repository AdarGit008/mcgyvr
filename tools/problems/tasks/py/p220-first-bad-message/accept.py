from solution import first_bad_message


def said(sender, kind):
    return {"from": sender, "kind": kind}


OPENING = [
    said("client", "HELLO"),
    said("server", "OFFER"),
    said("client", "CHOOSE"),
    said("server", "ACCEPT"),
]
CLOSING = [said("client", "BYE"), said("server", "BYE")]


def rejects(value):
    try:
        first_bad_message(value)
    except ValueError:
        return True
    return False


assert first_bad_message(OPENING + CLOSING) == -1, "an exchange with no data is whole"
assert (
    first_bad_message(
        OPENING + [said("client", "DATA"), said("server", "DATA")] + CLOSING
    )
    == -1
), "one round of data is whole"
assert (
    first_bad_message(
        OPENING
        + [
            said("client", "DATA"),
            said("server", "DATA"),
            said("client", "DATA"),
            said("server", "DATA"),
        ]
        + CLOSING
    )
    == -1
), "two rounds of data are whole"
assert (
    first_bad_message([said("client", "HELLO")]) == 1
), "an exchange that has only begun reports its length"
assert first_bad_message(OPENING) == 4, "an exchange that never says goodbye"
assert (
    first_bad_message(OPENING + [said("client", "BYE")]) == 5
), "the server's closing BYE is still owed"
assert (
    first_bad_message([said("server", "HELLO"), said("server", "OFFER")]) == 0
), "the wrong side opens"
assert (
    first_bad_message([said("client", "HELLO"), said("client", "OFFER")]) == 1
), "the right kind from the wrong side"
assert (
    first_bad_message(OPENING + [said("server", "DATA")]) == 4
), "the server cannot speak data first"
assert (
    first_bad_message(OPENING + [said("client", "DATA"), said("client", "BYE")]) == 5
), "the server owes an answer before goodbye"
assert (
    first_bad_message(OPENING + [said("client", "BYE"), said("client", "BYE")]) == 5
), "the client cannot answer its own goodbye"
assert (
    first_bad_message(OPENING + CLOSING + [said("client", "DATA")]) == 6
), "nothing may follow the closing BYE"

assert rejects("HELLO"), "an exchange that is not a list is rejected"
assert rejects([]), "an empty exchange is rejected"
assert rejects([["client", "HELLO"]]), "a message that is not a mapping is rejected"
assert rejects([said("proxy", "HELLO")]), "an unknown side is rejected"
assert rejects([said("client", "hello")]), "a kind in the wrong case is rejected"
assert rejects([said("client", "PING")]), "a kind outside the six names is rejected"

print("ok")
