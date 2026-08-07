def changed_cells(cells: dict[str, str], name: str, replacement: str) -> list[str]:
    if name not in cells:
        raise ValueError(f"unknown cell {name}")

    def evaluate(sheet: dict[str, str]) -> dict[str, int]:
        values: dict[str, int] = {}

        def value_of(cell: str) -> int:
            if cell not in values:
                raw = sheet[cell]
                if raw.startswith("="):
                    values[cell] = sum(
                        value_of(part.strip()) for part in raw[1:].split("+")
                    )
                else:
                    values[cell] = int(raw.strip())
            return values[cell]

        for cell in sheet:
            value_of(cell)
        return values

    before = evaluate(cells)
    after = evaluate({**cells, name: replacement})
    return sorted(cell for cell in cells if before[cell] != after[cell])
