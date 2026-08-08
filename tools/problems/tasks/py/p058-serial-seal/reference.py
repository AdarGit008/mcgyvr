def seal_serial(serial: str) -> str:
    if not isinstance(serial, str):
        raise ValueError("seal_serial expects a string")
    if len(serial) != 8 or not all("0" <= ch <= "9" for ch in serial):
        raise ValueError("serial must be exactly eight digits 0-9")
    weights = [3, 7, 1, 3, 7, 1, 3, 7]
    remainder = sum(int(ch) * w for ch, w in zip(serial, weights)) % 11
    return serial + ("K" if remainder == 10 else str(remainder))
