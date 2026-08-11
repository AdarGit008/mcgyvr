/** A word-to-line index for a plain-text note. */

export function wordsOfLine(line: string): string[] {
  const runs = line.toLowerCase().match(/[a-z0-9]+/g);
  if (runs === null) {
    return [];
  }
  return runs;
}

export function buildWordIndex(text: string): Record<string, number[]> {
  if (typeof text !== "string") {
    throw new Error("buildWordIndex expects a string");
  }
  const index: Record<string, number[]> = {};
  const rows = text.split("\n");
  for (let row = 1; row <= rows.length; row++) {
    for (const word of wordsOfLine(rows[row - 1])) {
      const numbers = index[word];
      if (numbers === undefined) {
        index[word] = [row];
        continue;
      }
      if (numbers[numbers.length - 1] !== row) {
        numbers.push(row);
      }
    }
  }
  return index;
}
