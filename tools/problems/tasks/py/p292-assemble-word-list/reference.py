import re

MARKER_LINE = re.compile(r"([a-z][a-z0-9_]*):$")
MARKER_NAME = re.compile(r"[a-z][a-z0-9_]*$")
HEAD = re.compile(r"([A-Z]+)(?:\s+(\S.*))?$")


def _register(chunk: str) -> int:
    found = re.fullmatch(r"r([0-7])", chunk)
    if found is None:
        raise ValueError(f"bad register: {chunk}")
    return int(found.group(1))


def _immediate(chunk: str) -> int:
    if re.fullmatch(r"0|[1-9][0-9]*", chunk) is None:
        raise ValueError(f"bad immediate: {chunk}")
    value = int(chunk)
    if value > 255:
        raise ValueError(f"immediate outside 0 through 255: {chunk}")
    return value


def _expect(operands: list[str], count: int, mnemonic: str) -> None:
    if len(operands) != count:
        raise ValueError(f"{mnemonic} takes {count} operands")


def assemble_word_list(lines: list[str]) -> list[int]:
    if not isinstance(lines, list):
        raise ValueError("assemble_word_list expects a list of lines")
    pieces: list[tuple[int, str | None]] = []
    markers: dict[str, int] = {}
    for raw in lines:
        if not isinstance(raw, str):
            raise ValueError("every source line must be a string")
        line = raw.strip()
        if line == "" or line.startswith(";"):
            continue
        planted = MARKER_LINE.fullmatch(line)
        if planted is not None:
            if planted.group(1) in markers:
                raise ValueError(f"marker planted twice: {planted.group(1)}")
            markers[planted.group(1)] = len(pieces)
            continue
        head = HEAD.fullmatch(line)
        if head is None:
            raise ValueError(f"line the format does not cover: {line}")
        mnemonic = head.group(1)
        rest = head.group(2)
        operands = [] if rest is None else [part.strip() for part in rest.split(",")]
        if mnemonic == "SET":
            _expect(operands, 2, "SET")
            word = 4096 + 256 * _register(operands[0]) + _immediate(operands[1])
            pieces.append((word, None))
        elif mnemonic == "ADD":
            _expect(operands, 2, "ADD")
            word = 8192 + 256 * _register(operands[0]) + _register(operands[1])
            pieces.append((word, None))
        elif mnemonic == "JZ":
            _expect(operands, 2, "JZ")
            target = operands[1]
            if MARKER_NAME.fullmatch(target) is None:
                raise ValueError(f"bad marker name: {target}")
            pieces.append((12288 + 256 * _register(operands[0]), target))
        elif mnemonic == "HALT":
            _expect(operands, 0, "HALT")
            pieces.append((16384, None))
        else:
            raise ValueError(f"unknown mnemonic: {mnemonic}")
    words: list[int] = []
    for at, (word, marker) in enumerate(pieces):
        if marker is None:
            words.append(word)
            continue
        if marker not in markers:
            raise ValueError(f"no line plants marker: {marker}")
        distance = markers[marker] - (at + 1)
        if distance < -128 or distance > 127:
            raise ValueError(f"distance outside -128 through 127: {distance}")
        words.append(word + (distance + 256 if distance < 0 else distance))
    return words
