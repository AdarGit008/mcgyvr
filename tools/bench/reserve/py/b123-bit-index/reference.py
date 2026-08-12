"""A rank/select index over a fixed bitmap of 32-bit words."""


def build_bit_index(words, length):
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise ValueError("length must be a non-negative integer")
    needed = (length + 31) // 32
    if not isinstance(words, list) or len(words) != needed:
        raise ValueError(f"expected {needed} words for {length} bits")
    for word in words:
        if isinstance(word, bool) or not isinstance(word, int):
            raise ValueError("words must be 32-bit integers")
        if word < 0 or word > 4294967295:
            raise ValueError("words must be 32-bit integers")
    used = length % 32
    if used != 0 and words[-1] >> used != 0:
        raise ValueError("set bit at or beyond length")
    prefix = [0]
    for word in words:
        prefix.append(prefix[-1] + bin(word).count("1"))
    return {"words": list(words), "length": length, "prefix": prefix}


def rank_ones(index, pos):
    if isinstance(pos, bool) or not isinstance(pos, int):
        raise ValueError("rank position out of range")
    if pos < 0 or pos > index["length"]:
        raise ValueError("rank position out of range")
    whole = pos // 32
    partial = pos % 32
    count = index["prefix"][whole]
    if partial > 0:
        count += bin(index["words"][whole] & ((1 << partial) - 1)).count("1")
    return count


def select_one(index, k):
    total = index["prefix"][-1]
    if isinstance(k, bool) or not isinstance(k, int) or k < 0 or k >= total:
        raise ValueError("select rank out of range")
    word_at = 0
    while index["prefix"][word_at + 1] <= k:
        word_at += 1
    remaining = k - index["prefix"][word_at]
    word = index["words"][word_at]
    for bit in range(32):
        if (word >> bit) & 1:
            if remaining == 0:
                return word_at * 32 + bit
            remaining -= 1
    raise ValueError("prefix table disagrees with its words")
