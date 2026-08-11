from solution import vat_back

assert vat_back(1200, 20) == 1000, "a fifth comes back off"
assert vat_back(1000, 0) == 1000, "no rate, no change"
assert vat_back(110, 10) == 100, "a tenth comes back off"
assert vat_back(0, 20) == 0, "nothing is taxed as nothing"
assert vat_back(1000, 20) == 833, "rounded down"
assert vat_back(100, 100) == 50, "a rate of a hundred halves it"
print("ok")
