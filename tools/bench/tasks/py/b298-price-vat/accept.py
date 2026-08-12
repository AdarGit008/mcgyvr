from solution import gross_price

assert gross_price(1000, 20) == 1200, "a fifth is added"
assert gross_price(999, 20) == 1198, "the tax is rounded down"
assert gross_price(500, 0) == 500, "no rate, no change"
assert gross_price(0, 20) == 0, "nothing is taxed as nothing"
assert gross_price(333, 10) == 366, "a tenth, rounded down"
assert gross_price(100, 100) == 200, "a rate of a hundred doubles it"
print("ok")
