"""A word-to-line index for a plain-text note."""

import re

WORD_RUN = re.compile(r"[a-z0-9]+")


def words_of_line(line):
    return WORD_RUN.findall(line.lower())


def build_word_index(text):
    if not isinstance(text, str):
        raise ValueError("build_word_index expects a string")
    index = {}
    rows = text.split("\n")
    for row, line in enumerate(rows, start=1):
        for word in words_of_line(line):
            numbers = index.get(word)
            if numbers is None:
                index[word] = [row]
            elif numbers[-1] != row:
                numbers.append(row)
    return index
