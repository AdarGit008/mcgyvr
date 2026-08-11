/** Gap widths that justify a paragraph's lines to a column. */
export function justifySpacing(
  width: number,
  lines: string[][],
): number[][] {
  if (!Number.isInteger(width) || width <= 0) {
    throw new Error("width must be a positive integer");
  }
  if (!Array.isArray(lines) || lines.length === 0) {
    throw new Error("a paragraph is a non-empty list of lines");
  }
  const spacing: number[][] = [];
  for (let row = 0; row < lines.length; row += 1) {
    const line = lines[row];
    if (!Array.isArray(line) || line.length === 0) {
      throw new Error("a line is a non-empty list of words");
    }
    let letters = 0;
    for (const word of line) {
      if (typeof word !== "string" || word === "") {
        throw new Error("a word must be a non-empty string");
      }
      if (word.includes(" ")) {
        throw new Error("a word must not contain spaces");
      }
      letters += word.length;
    }
    const gapCount = line.length - 1;
    const minWidth = letters + gapCount;
    if (minWidth > width) {
      throw new Error("a line must fit its width");
    }
    if (gapCount === 0 || row === lines.length - 1) {
      spacing.push(new Array(gapCount).fill(1));
    } else {
      const spare = width - letters;
      const base = Math.floor(spare / gapCount);
      const bump = spare % gapCount;
      const gaps: number[] = [];
      for (let i = 0; i < gapCount; i += 1) {
        gaps.push(i < bump ? base + 1 : base);
      }
      spacing.push(gaps);
    }
  }
  return spacing;
}
