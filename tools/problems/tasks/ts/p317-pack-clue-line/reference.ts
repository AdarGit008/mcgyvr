/** The clue's groups crowded as far to the left as they will go. */
export function packClueLine(width: number, clues: number[]): string {
  if (!Number.isInteger(width) || width < 1) {
    throw new Error("the width must be a whole number above zero");
  }
  if (!Array.isArray(clues)) {
    throw new Error("clues must be a list");
  }
  for (const clue of clues) {
    if (!Number.isInteger(clue) || clue < 1) {
      throw new Error("every clue must be a whole number above zero");
    }
  }
  let needed = 0;
  for (const clue of clues) {
    needed += clue;
  }
  if (clues.length > 0) {
    needed += clues.length - 1;
  }
  if (needed > width) {
    throw new Error("the clues cannot be drawn within this width");
  }
  const drawn = clues.map((clue) => "#".repeat(clue)).join(".");
  return drawn + ".".repeat(width - drawn.length);
}
