/** Fold shelf entries into a final count and a skipped-take tally. */
export function shelfCount(entries: Array<[string, number]>): [number, number] {
  let count = 0;
  let skipped = 0;
  for (const [kind, amount] of entries) {
    if (kind !== "add" && kind !== "take" && kind !== "fix") {
      throw new Error("unknown kind");
    }
    if (typeof amount !== "number" || !Number.isInteger(amount) || amount < 0) {
      throw new Error("amount must be a non-negative integer");
    }
    if (kind === "add") {
      count += amount;
    } else if (kind === "fix") {
      count = amount;
    } else if (amount > count) {
      skipped += 1;
    } else {
      count -= amount;
    }
  }
  return [count, skipped];
}
