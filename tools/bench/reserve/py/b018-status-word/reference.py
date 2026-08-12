"""Decode one 16-bit telemetry status word into its fields.

bit 15..12  channel (unsigned)
bit 11..2   reading (10-bit two's complement)
bit 1       stale flag
bit 0       even-parity bit over the whole word
"""

CHANNEL_SHIFT = 12
CHANNEL_MASK = 0xF
READING_SHIFT = 2
READING_MASK = 0x3FF
SIGN_BIT = 0x200
READING_SPAN = 0x400
STALE_SHIFT = 1
WORD_MAX = 0xFFFF


def decode_status_word(word):
    """Return {channel, reading, stale} after validating word and parity."""
    if isinstance(word, bool) or not isinstance(word, int):
        raise ValueError("decode_status_word expects an integer")
    if word < 0 or word > WORD_MAX:
        raise ValueError("status word must fit in 16 bits")
    ones = 0
    rest = word
    while rest:
        ones += rest & 1
        rest >>= 1
    if ones % 2:
        raise ValueError("status word fails even parity")
    channel = (word >> CHANNEL_SHIFT) & CHANNEL_MASK
    raw = (word >> READING_SHIFT) & READING_MASK
    reading = raw - READING_SPAN if raw >= SIGN_BIT else raw
    stale = bool((word >> STALE_SHIFT) & 1)
    return {"channel": channel, "reading": reading, "stale": stale}
