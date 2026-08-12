export function lineWidth(words: string[]): number {
  let width = 0;
  for (const word of words) width += word.length;
  return width + Math.max(words.length - 1, 0);
}

export function layoutWords(words: string[], width: number): string[][] {
  if (!Number.isInteger(width) || width <= 0) {
    throw new Error("width must be a positive integer");
  }
  const lines: string[][] = [];
  let current: string[] = [];
  for (const word of words) {
    if (typeof word !== "string" || word.length === 0) {
      throw new Error("words must be non-empty strings");
    }
    if (word.length > width) {
      throw new Error("word wider than the column: " + word);
    }
    if (current.length === 0 || lineWidth([...current, word]) <= width) {
      current.push(word);
    } else {
      lines.push(current);
      current = [word];
    }
  }
  if (current.length > 0) lines.push(current);
  return lines;
}
