/**
 * One 16-bit telemetry status word:
 *
 *   bit 15..12  channel (unsigned)
 *   bit 11..2   reading (10-bit two's complement)
 *   bit 1       stale flag
 *   bit 0       even-parity bit over the whole word
 */
const CHANNEL_SHIFT = 12;
const CHANNEL_MASK = 0xf;
const READING_SHIFT = 2;
const READING_MASK = 0x3ff;
const SIGN_BIT = 0x200;
const READING_SPAN = 0x400;
const STALE_SHIFT = 1;
const WORD_MAX = 0xffff;

const NIBBLE_ONES = [0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4];

function oneBits(word: number): number {
  let count = 0;
  for (let rest = word; rest > 0; rest >>= 4) {
    count += NIBBLE_ONES[rest & 0xf];
  }
  return count;
}

export function decodeStatusWord(
  word: number,
): { channel: number; reading: number; stale: boolean } {
  if (typeof word !== "number" || !Number.isInteger(word)) {
    throw new Error("decodeStatusWord expects an integer");
  }
  if (word < 0 || word > WORD_MAX) {
    throw new Error("status word must fit in 16 bits");
  }
  if (oneBits(word) % 2 !== 0) {
    throw new Error("status word fails even parity");
  }
  const channel = (word >> CHANNEL_SHIFT) & CHANNEL_MASK;
  const raw = (word >> READING_SHIFT) & READING_MASK;
  const reading = raw >= SIGN_BIT ? raw - READING_SPAN : raw;
  const stale = ((word >> STALE_SHIFT) & 1) === 1;
  return { channel, reading, stale };
}
