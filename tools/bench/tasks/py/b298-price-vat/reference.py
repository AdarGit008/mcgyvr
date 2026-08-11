def gross_price(net: int, rate: int) -> int:
    """A net price with a whole-percent tax added, in whole pence."""
    return net + net * rate // 100
