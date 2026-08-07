def _charged(balance: int, rate: int) -> int:
    return (balance * rate + 5000) // 10000


def level_payment_schedule(opening: int, rate: int, payment: int, terms: int) -> list[list[int]]:
    for value in (opening, rate, payment, terms):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("opening, rate, payment and terms must be whole numbers")
    if opening <= 0 or payment <= 0 or terms <= 0:
        raise ValueError("opening, payment and terms must be above zero")
    if rate < 0:
        raise ValueError("rate must not fall below zero")
    if payment <= _charged(opening, rate):
        raise ValueError("payment must exceed the first period's charge")

    rows: list[list[int]] = []
    balance = opening
    for period in range(1, terms + 1):
        charge = _charged(balance, rate)
        if period == terms or payment >= charge + balance:
            rows.append([charge + balance, charge, balance, 0])
            break
        bite = payment - charge
        balance -= bite
        rows.append([payment, charge, bite, balance])
    return rows
