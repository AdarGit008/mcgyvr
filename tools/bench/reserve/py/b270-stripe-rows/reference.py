def stripe_rows(rows: int, colours: list) -> list:
    painted = []
    for i in range(rows):
        painted.append(colours[i % len(colours)])
    return painted
