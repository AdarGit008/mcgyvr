"""Three-way ledger merge: apply both sides' edits against a common base."""


def merge_ledgers(base, ours, theirs):
    def read_ledger(pairs):
        if not isinstance(pairs, list):
            raise ValueError("a ledger must be a list of [account, cents] pairs")
        ledger = {}
        for pair in pairs:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("a ledger entry must be an [account, cents] pair")
            account, cents = pair
            if not isinstance(account, str) or account == "":
                raise ValueError("account name must be a non-empty string")
            if isinstance(cents, bool) or not isinstance(cents, int):
                raise ValueError("cents must be an integer")
            if account in ledger:
                raise ValueError("account repeated: " + account)
            ledger[account] = cents
        return ledger

    before = read_ledger(base)
    left = read_ledger(ours)
    right = read_ledger(theirs)
    merged = []
    for name in sorted(set(before) | set(left) | set(right)):
        in_base = name in before
        in_left = name in left
        in_right = name in right
        if in_base and in_left and in_right:
            start = before[name]
            left_delta = left[name] - start
            right_delta = right[name] - start
            merged.append([name, start + left_delta + right_delta])
        elif not in_base and in_left and in_right:
            merged.append([name, left[name] + right[name]])
        elif not in_base and (in_left or in_right):
            side = left if in_left else right
            merged.append([name, side[name]])
        elif in_left or in_right:
            side = left if in_left else right
            survivor = side[name]
            if survivor != before[name]:
                merged.append([name, survivor])
    return merged
