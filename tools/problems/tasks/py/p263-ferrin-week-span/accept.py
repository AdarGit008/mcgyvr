from solution import ferrin_week_span

assert ferrin_week_span(2026, 1) == ["2026-01-03", "2026-01-09"], "week one opens on the first Saturday"
assert ferrin_week_span(2026, 0) == ["2026-01-01", "2026-01-02"], "the stub week before it"
assert ferrin_week_span(2026, 2) == ["2026-01-10", "2026-01-16"], "an ordinary interior week"
assert ferrin_week_span(2026, 52) == ["2026-12-26", "2026-12-31"], "the closing week stops at December 31"
assert ferrin_week_span(2024, 0) == ["2024-01-01", "2024-01-05"], "a five day stub week"
assert ferrin_week_span(2024, 9) == ["2024-03-02", "2024-03-08"], "a leap year week straddling February"
assert ferrin_week_span(2024, 52) == ["2024-12-28", "2024-12-31"], "a leap year closing week is clipped too"
assert ferrin_week_span(2022, 1) == ["2022-01-01", "2022-01-07"], "a year opening on a Saturday starts at week one"
assert ferrin_week_span(2022, 53) == ["2022-12-31", "2022-12-31"], "a closing week of a single day"
assert ferrin_week_span(2021, 52) == ["2021-12-25", "2021-12-31"], "a closing week that happens to run the full seven"
assert ferrin_week_span(2000, 1) == ["2000-01-01", "2000-01-07"], "a leap century opening on a Saturday"
assert ferrin_week_span(1900, 0) == ["1900-01-01", "1900-01-05"], "a common century keeps its stub week"


def rejects(year, week):
    try:
        ferrin_week_span(year, week)
    except ValueError:
        return True
    return False


assert rejects(2022, 0), "no stub week when the year opens on a Saturday"
assert rejects(2026, 53), "a week the year never reaches"
assert rejects(2022, 54), "one past a fifty-three week year"
assert rejects(2026, -1), "a negative week"
assert rejects(2026, 1.5), "a fractional week"
assert rejects(0, 1), "year zero"
assert rejects(10000, 1), "a year past the ceiling"
assert rejects("2026", 1), "a year that is not a number"
print("ok")
