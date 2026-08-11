from solution import line_cost, basket_cost

assert line_cost(250, 2) == 500, "price times quantity"
assert line_cost(100, 0) == 0, "none of it costs nothing"
assert basket_cost([{"price": 250, "quantity": 2}], 0) == 500, "no discount"
assert (
    basket_cost(
        [{"price": 250, "quantity": 2}, {"price": 100, "quantity": 3}], 10
    )
    == 720
), "the discount comes off the whole basket"
assert basket_cost([], 25) == 0, "an empty basket"
assert basket_cost([{"price": 99, "quantity": 1}], 10) == 89, "rounded down"
print("ok")
