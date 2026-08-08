export function reassembleStream(
  total: number,
  fragments: Array<[number, string]>,
): string {
  if (!Number.isInteger(total) || total < 0) {
    throw new Error("total must be a non-negative integer");
  }
  const slots: Array<string | null> = Array(total).fill(null);
  for (const [offset, text] of fragments) {
    if (!Number.isInteger(offset) || offset < 0) {
      throw new Error("offset must be a non-negative integer");
    }
    if (offset + text.length > total) {
      throw new Error("fragment runs past the declared end");
    }
    for (let k = 0; k < text.length; k++) {
      const existing = slots[offset + k];
      if (existing !== null && existing !== text[k]) {
        throw new Error(`conflict at position ${offset + k}`);
      }
      slots[offset + k] = text[k];
    }
  }
  if (slots.some((slot) => slot === null)) {
    throw new Error("uncovered position");
  }
  return slots.join("");
}
