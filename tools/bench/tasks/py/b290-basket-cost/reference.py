def line_cost(price: int, quantity: int) -> int:
    return price * quantity


def basket_cost(lines: list, discount: int) -> int:
    total = 0
    for line in lines:
        total += line_cost(line["price"], line["quantity"])
    return total * (100 - discount) // 100
