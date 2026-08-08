import re

CARD = re.compile(r"[2-9][knpt]")


def judge_vane_trick(play: dict) -> dict:
    """Who took one Vane trick, and which seats reneged on the called plume."""
    if not isinstance(play, dict):
        raise ValueError("the play must be a mapping")
    trump = play.get("trump")
    if not isinstance(trump, str) or trump not in ("k", "n", "p", "t", "bare"):
        raise ValueError("trump must be a plume letter or the word bare")
    lead = play.get("lead")
    if not isinstance(lead, int) or isinstance(lead, bool) or lead < 0 or lead > 3:
        raise ValueError("lead must be a seat from 0 to 3")
    holdings = play.get("holdings")
    if not isinstance(holdings, list) or len(holdings) != 4:
        raise ValueError("holdings must be a list of exactly four holdings")
    seen = set()
    for holding in holdings:
        if not isinstance(holding, list) or not holding:
            raise ValueError("a holding must be a non-empty list of cards")
        for card in holding:
            if not isinstance(card, str) or CARD.fullmatch(card) is None:
                raise ValueError("a card must be a heat from 2 to 9 and a plume letter")
            if card in seen:
                raise ValueError("one card sits in two holdings")
            seen.add(card)
    played = play.get("played")
    if not isinstance(played, list) or len(played) != 4:
        raise ValueError("played must be a list of exactly four cards")
    seats = []
    for place in range(4):
        card = played[place]
        if not isinstance(card, str) or CARD.fullmatch(card) is None:
            raise ValueError("a card must be a heat from 2 to 9 and a plume letter")
        seat = (lead + place) % 4
        if card not in holdings[seat]:
            raise ValueError("a seat laid a card it never held")
        seats.append(seat)

    called = played[0][1]
    revokes = []
    for place in range(1, 4):
        if played[place][1] == called:
            continue
        if any(held[1] == called for held in holdings[seats[place]]):
            revokes.append(seats[place])
    revokes.sort()

    standing = [place for place in range(4) if seats[place] not in revokes]
    wanted = (
        trump
        if trump != "bare" and any(played[place][1] == trump for place in standing)
        else called
    )
    best = -1
    for place in standing:
        if played[place][1] != wanted:
            continue
        if best < 0 or int(played[place][0]) > int(played[best][0]):
            best = place

    return {"taker": seats[best], "revokes": revokes}
