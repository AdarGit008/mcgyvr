export function wrapCost(words: string[], width: number): number {
  if (typeof width !== "number" || !Number.isInteger(width) || width < 1) {
    throw new Error("width must be a positive whole number");
  }
  if (words.length === 0) {
    throw new Error("there is nothing to wrap");
  }
  for (const word of words) {
    if (word.length === 0) {
      throw new Error("an empty word cannot be wrapped");
    }
    if (word.length > width) {
      throw new Error(`"${word}" does not fit on any line`);
    }
  }
  const count = words.length;
  const best: number[] = new Array(count + 1).fill(Infinity);
  best[count] = 0;
  for (let start = count - 1; start >= 0; start--) {
    let length = 0;
    for (let end = start; end < count; end++) {
      length += words[end].length + (end > start ? 1 : 0);
      if (length > width) {
        break;
      }
      const slack = width - length;
      const candidate = slack * slack + best[end + 1];
      if (candidate < best[start]) {
        best[start] = candidate;
      }
    }
  }
  return best[0];
}
