export function mendShards(copies: Array<Array<number | null>>): number[] {
  if (!Array.isArray(copies) || copies.length === 0) {
    throw new Error("the list of copies must be non-empty");
  }
  const width = copies[0].length;
  for (const copy of copies) {
    if (!Array.isArray(copy) || copy.length !== width) {
      throw new Error("copies differ in length");
    }
    for (const slot of copy) {
      if (slot !== null && (!Number.isInteger(slot) || (slot as number) < 0)) {
        throw new Error("a slot must be a non-negative integer or null");
      }
    }
  }
  const mended: number[] = [];
  for (let position = 0; position < width; position++) {
    const counts = new Map<number, number>();
    const earliest = new Map<number, number>();
    for (let index = 0; index < copies.length; index++) {
      const slot = copies[index][position];
      if (slot === null) {
        continue;
      }
      counts.set(slot, (counts.get(slot) ?? 0) + 1);
      if (!earliest.has(slot)) {
        earliest.set(slot, index);
      }
    }
    if (counts.size === 0) {
      mended.push(-1);
      continue;
    }
    let winner = -1;
    for (const [value, count] of counts) {
      if (winner === -1) {
        winner = value;
        continue;
      }
      const lead = counts.get(winner) as number;
      if (
        count > lead ||
        (count === lead &&
          (earliest.get(value) as number) < (earliest.get(winner) as number))
      ) {
        winner = value;
      }
    }
    mended.push(winner);
  }
  return mended;
}
