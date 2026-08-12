/** Lay two blocks of text side by side with a fixed gap between them. */
export function pairColumns(left: string[], right: string[], gap: number): string[] {
  if (!Number.isInteger(gap) || gap < 0) {
    throw new Error("gap must be a non-negative integer");
  }
  let width = 0;
  for (const line of left) {
    width = Math.max(width, line.length);
  }
  const rows = Math.max(left.length, right.length);
  const laid: string[] = [];
  for (let row = 0; row < rows; row += 1) {
    const near = row < left.length ? left[row] : "";
    const far = row < right.length ? right[row] : "";
    let line = near + " ".repeat(width - near.length + gap) + far;
    while (line.endsWith(" ")) {
      line = line.slice(0, -1);
    }
    laid.push(line);
  }
  return laid;
}
