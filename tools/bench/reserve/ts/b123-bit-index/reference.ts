/** A rank/select index over a fixed bitmap of 32-bit words. */

type BitIndex = { words: number[]; length: number; prefix: number[] };

function onesInWord(word: number): number {
  let count = 0;
  let rest = word;
  while (rest !== 0) {
    count += rest & 1;
    rest >>>= 1;
  }
  return count;
}

export function buildBitIndex(words: number[], length: number): BitIndex {
  if (!Number.isInteger(length) || length < 0) {
    throw new Error("length must be a non-negative integer");
  }
  const needed = Math.ceil(length / 32);
  if (!Array.isArray(words) || words.length !== needed) {
    throw new Error(`expected ${needed} words for ${length} bits`);
  }
  for (const word of words) {
    if (!Number.isInteger(word) || word < 0 || word > 4294967295) {
      throw new Error("words must be 32-bit integers");
    }
  }
  const used = length % 32;
  if (used !== 0 && words[needed - 1] >>> used !== 0) {
    throw new Error("set bit at or beyond length");
  }
  const prefix: number[] = [0];
  for (const word of words) {
    prefix.push(prefix[prefix.length - 1] + onesInWord(word));
  }
  return { words: [...words], length, prefix };
}

export function rankOnes(index: BitIndex, pos: number): number {
  if (!Number.isInteger(pos) || pos < 0 || pos > index.length) {
    throw new Error("rank position out of range");
  }
  const whole = Math.floor(pos / 32);
  const partial = pos % 32;
  let count = index.prefix[whole];
  if (partial > 0) {
    count += onesInWord(index.words[whole] & (2 ** partial - 1));
  }
  return count;
}

export function selectOne(index: BitIndex, k: number): number {
  const total = index.prefix[index.prefix.length - 1];
  if (!Number.isInteger(k) || k < 0 || k >= total) {
    throw new Error("select rank out of range");
  }
  let wordAt = 0;
  while (index.prefix[wordAt + 1] <= k) {
    wordAt += 1;
  }
  let remaining = k - index.prefix[wordAt];
  const word = index.words[wordAt];
  for (let bit = 0; bit < 32; bit += 1) {
    if ((word >>> bit) & 1) {
      if (remaining === 0) {
        return wordAt * 32 + bit;
      }
      remaining -= 1;
    }
  }
  throw new Error("prefix table disagrees with its words");
}
