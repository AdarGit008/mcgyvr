def range_text(first: int, last: int) -> str:
    if first == last:
        return str(first)
    return str(first) + "-" + str(last)


def span_list(numbers: list) -> list:
    spans = []
    start = 0
    for i in range(1, len(numbers) + 1):
        if i == len(numbers) or numbers[i] != numbers[i - 1] + 1:
            spans.append(range_text(numbers[start], numbers[i - 1]))
            start = i
    return spans
