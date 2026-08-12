def crate_fill(items: int, crates: int) -> list:
    sizes = []
    for i in range(crates):
        sizes.append(items // crates + (1 if i < items % crates else 0))
    return sizes


def crate_total(sizes: list) -> int:
    return sum(sizes)
