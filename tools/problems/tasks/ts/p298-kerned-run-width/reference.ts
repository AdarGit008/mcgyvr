export function kernedRunWidth(
  text: string,
  widths: Record<string, number>,
  kerns: [string, number][],
  tracking: number,
): number {
  if (typeof text !== "string") {
    throw new Error("kernedRunWidth expects a string run");
  }
  if (widths === null || typeof widths !== "object" || Array.isArray(widths)) {
    throw new Error("widths must be a plain mapping");
  }
  for (const letter of Object.keys(widths)) {
    const width = widths[letter];
    if (!Number.isInteger(width) || width < 0) {
      throw new Error("a width is a whole number of zero or more: " + letter);
    }
  }
  if (!Array.isArray(kerns)) {
    throw new Error("kerns must be a table list");
  }
  const table = new Map<string, number>();
  for (const row of kerns) {
    if (!Array.isArray(row) || row.length !== 2) {
      throw new Error("a table row is a couple and a number");
    }
    const [couple, adjust] = row;
    if (typeof couple !== "string" || couple.length !== 2) {
      throw new Error("a couple is exactly two characters: " + String(couple));
    }
    if (!Number.isInteger(adjust)) {
      throw new Error("a kern is a whole number");
    }
    if (!table.has(couple)) {
      table.set(couple, adjust);
    }
  }
  if (!Number.isInteger(tracking)) {
    throw new Error("tracking is a whole number");
  }
  let total = 0;
  for (const letter of text) {
    if (!Object.prototype.hasOwnProperty.call(widths, letter)) {
      throw new Error("no width for " + letter);
    }
    total += widths[letter];
  }
  for (let at = 1; at < text.length; at++) {
    const couple = text.slice(at - 1, at + 1);
    total += tracking;
    if (table.has(couple)) {
      total += table.get(couple);
    }
  }
  if (total < 0) {
    throw new Error("the run measures below zero");
  }
  return total;
}
