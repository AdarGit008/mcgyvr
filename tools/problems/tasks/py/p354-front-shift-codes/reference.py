def shift_front_codes(alphabet: str, message: str) -> list:
    if not isinstance(alphabet, str):
        raise ValueError("the alphabet must be a string")
    if len(alphabet) == 0:
        raise ValueError("the alphabet must not be empty")
    row = list(alphabet)
    if len(set(row)) != len(row):
        raise ValueError("the alphabet carries a character twice over")
    if not isinstance(message, str):
        raise ValueError("the message must be a string")
    places = []
    for character in message:
        if character not in row:
            raise ValueError("the message holds a character the alphabet lacks")
        place = row.index(character)
        places.append(place)
        row.pop(place)
        row.insert(0, character)
    return places
