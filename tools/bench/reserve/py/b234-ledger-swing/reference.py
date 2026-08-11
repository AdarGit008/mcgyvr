def ledger_swing(balances: list) -> int:
    widest = 0
    for i in range(1, len(balances)):
        swing = abs(balances[i] - balances[i - 1])
        if swing > widest:
            widest = swing
    return widest
