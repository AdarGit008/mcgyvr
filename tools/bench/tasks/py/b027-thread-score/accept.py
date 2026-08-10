from solution import count_awarded, prune_deleted, thread_depth, thread_score


def c(score, deleted=False, *replies):
    return {"score": score, "deleted": deleted, "replies": list(replies)}


def rejects(comment):
    try:
        thread_score(comment)
    except ValueError:
        return True
    return False


assert thread_score(c(5)) == 5, "lone comment scores itself"
assert thread_score(c(1, False, c(2), c(3))) == 6, "direct replies count"
assert thread_score(c(1, False, c(2, False, c(4, False, c(8))))) == 15, "deep nesting counts"
assert thread_score(c(7, True, c(2))) == 2, "deleted root contributes nothing"
assert thread_score(c(1, False, c(10, True, c(4)))) == 5, "deleted middle keeps its replies"
assert thread_score(c(-3, False, c(5))) == 2, "negative scores are summed"
assert thread_score(c(9, True)) == 0, "deleted lone comment is zero"
assert rejects(c(2.5)), "fractional score is rejected"
assert rejects(c(True)), "boolean score is rejected"
assert rejects(c(1, False, c(2, False, c("x")))), "deep bad score is rejected"
assert thread_depth(c(1)) == 1, "lone comment has depth 1"
assert thread_depth(c(1, False, c(2), c(3, False, c(4)))) == 3, "depth follows the longest chain"
assert count_awarded(c(5, False, c(3), c(8, True, c(10))), 5) == 2, "deleted comments never awarded"
assert count_awarded(c(1), 5) == 0, "no awards below the bar"
assert prune_deleted(c(4, True)) is None, "childless deleted thread prunes away"
assert prune_deleted(c(1, False, c(2, True), c(3))) == c(1, False, c(3)), "childless deleted reply drops"
assert prune_deleted(c(1, True, c(2, True, c(5)))) == c(1, True, c(2, True, c(5))), "chains to live leaves stay"
print("ok")
