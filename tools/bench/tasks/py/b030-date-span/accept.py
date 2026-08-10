from solution import span_days

assert span_days([2024, 5, 10], [2024, 5, 10]) == 0, "equal dates span zero"
assert span_days([2024, 5, 10], [2024, 5, 11]) == 1, "next day spans one"
assert span_days([2023, 1, 31], [2023, 2, 1]) == 1, "across a month end"
assert span_days([2023, 2, 28], [2023, 3, 1]) == 1, "plain February has 28 days"
assert span_days([2024, 2, 28], [2024, 3, 1]) == 2, "leap February has 29 days"
assert span_days([1900, 2, 28], [1900, 3, 1]) == 1, "1900 is not a leap year"
assert span_days([2000, 2, 28], [2000, 3, 1]) == 2, "2000 is a leap year"
assert span_days([2023, 1, 1], [2024, 1, 1]) == 365, "a plain year"
assert span_days([1899, 12, 31], [1901, 1, 1]) == 366, "a span across 1900"
assert span_days([2024, 2, 29], [2024, 3, 1]) == 1, "leap day is a real date"


def rejects(start, end):
    try:
        span_days(start, end)
    except ValueError:
        return True
    return False


assert rejects([2024, 1, 2], [2024, 1, 1]), "start after end is rejected"
assert rejects([2024, 0, 10], [2024, 1, 1]), "month zero is rejected"
assert rejects([2024, 13, 1], [2025, 1, 1]), "month thirteen is rejected"
assert rejects([2024, 1, 0], [2024, 2, 1]), "day zero is rejected"
assert rejects([2023, 4, 31], [2023, 5, 1]), "April the 31st is rejected"
assert rejects([2023, 2, 29], [2023, 3, 1]), "February 29 outside a leap year"
assert rejects([2024, 1, 1.5], [2024, 2, 1]), "fractional component is rejected"
print("ok")
