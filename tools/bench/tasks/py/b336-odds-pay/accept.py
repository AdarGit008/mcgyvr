from solution import payout, settle_all


def rejects(stake, odds):
    try:
        payout(stake, odds)
    except Exception:
        return True
    return False


assert payout(10, 3) == 30, "stake times odds"
assert payout(0, 5) == 0, "nothing staked, nothing returned"
assert settle_all([{"stake": 10, "odds": 3, "won": True}]) == 30, "one winner"
assert settle_all([{"stake": 10, "odds": 3, "won": False}]) == 0, "one loser"
assert settle_all([]) == 0, "no bets at all"
assert (
    settle_all(
        [
            {"stake": 5, "odds": 2, "won": True},
            {"stake": 5, "odds": 2, "won": False},
            {"stake": 1, "odds": 10, "won": True},
        ]
    )
    == 20
), "only the winners count"
assert rejects(-1, 2), "a negative stake is rejected"
print("ok")
