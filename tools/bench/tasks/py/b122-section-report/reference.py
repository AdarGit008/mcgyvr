"""A sectioned sales report: item lines, subtotals, and a ranked summary."""


def section_report(rows):
    def ranked(entry):
        return (-entry[2], entry[0])

    def checked(row):
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("a row must be a [section, label, amount] triple")
        section, label, amount = row
        if not isinstance(section, str) or section == "":
            raise ValueError("section must be a non-empty string")
        if not isinstance(label, str) or label == "":
            raise ValueError("label must be a non-empty string")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError("amount must be an integer")
        return section, label, amount

    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    order = []
    items = {}
    for row in rows:
        section, label, amount = checked(row)
        if section not in items:
            order.append(section)
            items[section] = []
        items[section].append([label, amount])

    lines = []
    sections = []
    grand = 0
    for section in order:
        bucket = items[section]
        subtotal = 0
        for label, amount in bucket:
            lines.append(["item", section, label, amount])
            subtotal += amount
        lines.append(["section", section, "", subtotal])
        sections.append([section, len(bucket), subtotal])
        grand += subtotal

    lines.append(["grand", "", "", grand])
    sections.sort(key=ranked)
    return {"lines": lines, "sections": sections, "grand": grand}
