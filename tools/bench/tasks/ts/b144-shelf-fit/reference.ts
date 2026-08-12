/** How many leading books fit on one shelf, strictly in arrival order. */
export function shelfFit(widths: number[], shelf: number): number {
  if (!Array.isArray(widths)) throw new Error("shelfFit expects a list of spine widths");
  if (!Number.isInteger(shelf) || shelf < 0) throw new Error("shelf must be a non-negative integer");
  for (const width of widths) {
    if (!Number.isInteger(width) || width < 1) throw new Error("every spine width must be a positive integer");
  }
  let used = 0;
  let count = 0;
  for (const width of widths) {
    if (used + width > shelf) break;
    used += width;
    count += 1;
  }
  return count;
}
