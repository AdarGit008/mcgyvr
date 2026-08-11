from solution import cut_roll

assert cut_roll(4, [(2, 5)]) == {"takings": 10, "pieces": [2, 2]}, "a roll is filled with as many paying pieces as it holds"
assert cut_roll(5, [(3, 7)]) == {"takings": 7, "pieces": [3]}, "metres no piece can use are left as scrap"
assert cut_roll(2, [(1, 3), (2, 6)]) == {"takings": 6, "pieces": [2]}, "a tie in takings goes to the longer piece"
assert cut_roll(7, [(3, 8), (4, 9)]) == {"takings": 17, "pieces": [4, 3]}, "mixed pieces beat repeating the best-paying one"
assert cut_roll(0, [(2, 5)]) == {"takings": 0, "pieces": []}, "a roll of no metres fetches nothing"
assert cut_roll(2, [(5, 9)]) == {"takings": 0, "pieces": []}, "a roll no piece fits fetches nothing"


def rejects(*args):
    try:
        cut_roll(*args)
    except Exception:
        return True
    return False


assert rejects(-1, [(2, 5)]), "a negative roll length is rejected"
print("ok")
