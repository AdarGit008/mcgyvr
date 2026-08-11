def net_pay(gross: int, rate: int, fee: int) -> int:
    """Gross pay less a percentage and then a flat fee."""
    after_rate = gross - gross * rate // 100
    return max(after_rate - fee, 0)
