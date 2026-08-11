/** Pull order lines from a shelf, refusing any pull the stock cannot honour. */
export function drawStock(shelf: Record<string, number>, order: [string, number][]): Record<string, number> {
  for (const [item, count] of Object.entries(shelf)) {
    if (!Number.isInteger(count) || count < 0) throw new Error("bad shelf count for " + item);
  }
  if (!Array.isArray(order)) throw new Error("drawStock expects a list of order lines");
  const left = { ...shelf };
  for (const [item, count] of order) {
    if (!Number.isInteger(count) || count < 1) throw new Error("line count must be a positive integer");
    if (!(item in left) || count > left[item]) throw new Error("cannot pull " + count + " of " + item);
    left[item] -= count;
  }
  return left;
}
