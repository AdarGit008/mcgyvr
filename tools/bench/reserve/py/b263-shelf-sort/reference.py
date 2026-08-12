import re


def shelf_sort(labels: list) -> list:
    def order(pair):
        return int(re.sub(r"^[^0-9]*", "", pair[1])), pair[0]

    return [label for _, label in sorted(enumerate(labels), key=order)]
