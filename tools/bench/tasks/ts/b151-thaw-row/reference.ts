/** Melt a row of ice one simultaneous step at a time. */
export function thawRow(row: string, steps: number): string {
  if (typeof row !== "string" || row.length === 0) {
    throw new Error("thawRow expects a non-empty string row");
  }
  if (!/^[#.]+$/.test(row)) {
    throw new Error("row may hold only # and . cells");
  }
  if (!Number.isInteger(steps) || steps < 0) {
    throw new Error("steps must be a non-negative whole number");
  }
  let cells = row;
  for (let step = 0; step < steps; step++) {
    const padded = "." + cells + ".";
    cells = [...cells].map((_, i) => (padded.slice(i, i + 3) === "###" ? "#" : ".")).join("");
  }
  return cells;
}
