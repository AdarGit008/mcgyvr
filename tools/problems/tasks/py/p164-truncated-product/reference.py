def _check_polynomial(poly: list[int]) -> None:
    if not isinstance(poly, list):
        raise ValueError("a polynomial must be a list")
    for coefficient in poly:
        if isinstance(coefficient, bool) or not isinstance(coefficient, int):
            raise ValueError("every coefficient must be a whole number")
    if poly and poly[-1] == 0:
        raise ValueError("a canonical polynomial never ends in a zero coefficient")


def truncated_product(left: list[int], right: list[int], cap: int) -> list[int]:
    _check_polynomial(left)
    _check_polynomial(right)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise ValueError("cap must be a whole number of at least zero")
    if not left or not right:
        return []
    width = min(len(left) + len(right) - 1, cap + 1)
    product = [0] * width
    for i, one in enumerate(left):
        for j, other in enumerate(right):
            if i + j < width:
                product[i + j] += one * other
    while product and product[-1] == 0:
        product.pop()
    return product
