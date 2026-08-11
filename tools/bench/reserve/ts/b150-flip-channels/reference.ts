/** Flip the packed channel switches lo through hi of a 16-channel board word. */
export function flipChannels(word: number, lo: number, hi: number): number {
  if (!Number.isInteger(word) || word < 0 || word > 65535) {
    throw new Error("word must be an integer from 0 to 65535");
  }
  for (const bound of [lo, hi]) {
    if (!Number.isInteger(bound) || bound < 0 || bound > 15) {
      throw new Error("channel bounds must be integers from 0 to 15");
    }
  }
  if (lo > hi) {
    throw new Error("lo must not exceed hi");
  }
  const span = ((1 << (hi - lo + 1)) - 1) << lo;
  return word ^ span;
}
