def bill_split(total: int, diners: int) -> list:
    share = total // diners
    shares = [share] * diners
    shares[0] += total - share * diners
    return shares
