def find_split_parcels(plan: list) -> list:
    if not isinstance(plan, list) or not plan:
        raise ValueError("the map must carry at least one row")
    height = len(plan)
    if not isinstance(plan[0], str):
        raise ValueError("every row must be a string")
    width = len(plan[0])
    if width == 0:
        raise ValueError("the map must carry at least one square")
    for row in plan:
        if not isinstance(row, str):
            raise ValueError("every row must be a string")
        if len(row) != width:
            raise ValueError("every row must share the width of the first")
        for square in row:
            if square != "." and not ("A" <= square <= "Z"):
                raise ValueError("unusable square marking: " + square)

    claimed = sum(1 for row in plan for square in row if square != ".")
    if claimed == 0:
        raise ValueError("the map claims not one square")

    walked = [[False] * width for _ in range(height)]
    pieces = {}
    for row in range(height):
        for column in range(width):
            letter = plan[row][column]
            if letter == "." or walked[row][column]:
                continue
            pieces[letter] = pieces.get(letter, 0) + 1
            stack = [(row, column)]
            walked[row][column] = True
            while stack:
                r, c = stack.pop()
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if nr < 0 or nr >= height or nc < 0 or nc >= width:
                        continue
                    if walked[nr][nc] or plan[nr][nc] != letter:
                        continue
                    walked[nr][nc] = True
                    stack.append((nr, nc))

    return [
        letter + ":" + str(pieces[letter])
        for letter in sorted(pieces)
        if pieces[letter] > 1
    ]
