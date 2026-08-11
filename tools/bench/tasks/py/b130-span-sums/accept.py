from solution import add_spans, format_span, parse_span

assert parse_span("2yd 1ft 4in") == 88, "a full span totals in inches"
assert parse_span("17in") == 17, "an unnormalized value is accepted"
assert parse_span("0in") == 0, "a zero span is zero inches"
assert parse_span("3yd 11in") == 119, "a middle unit may be left out"
assert format_span(88) == "2yd 1ft 4in", "inches render largest unit first"
assert format_span(0) == "0in", "zero inches render as 0in"
assert format_span(47) == "1yd 11in", "a zero-valued part is left out"
assert add_spans("1ft 6in", "8in") == "2ft 2in", "a sum carries inches into feet"
assert add_spans("1yd 2ft 11in", "1in") == "2yd", "a sum can carry into the yards"


def rejects(callable_, *args):
    try:
        callable_(*args)
    except ValueError:
        return True
    return False


assert rejects(parse_span, 4), "a non-string span is rejected"
assert rejects(parse_span, ""), "an empty span is rejected"
assert rejects(parse_span, "4m"), "an unknown unit is rejected"
assert rejects(parse_span, "1in 1ft"), "units out of order are rejected"
assert rejects(parse_span, "1ft 2ft"), "a repeated unit is rejected"
assert rejects(parse_span, "12"), "a bare value is rejected"
assert rejects(parse_span, "ft"), "a bare unit is rejected"
assert rejects(parse_span, "01ft"), "a leading zero is rejected"
assert rejects(format_span, -3), "negative inches are rejected"
print("ok")
