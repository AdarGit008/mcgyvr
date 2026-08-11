/** Lay a notice's text into placard lines. */

export function placardLines(text: string, width: number): string[] {
  if (typeof text !== "string" || text.length === 0) {
    throw new Error("placardLines expects a non-empty string");
  }
  if (!Number.isInteger(width) || width <= 0) {
    throw new Error("width must be a positive integer");
  }
  if (text.startsWith(" ") || text.endsWith(" ") || text.includes("  ")) {
    throw new Error("words must be separated by single spaces");
  }
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(" ")) {
    if (word.length > width) {
      throw new Error("word wider than the placard: " + word);
    }
    if (line.length === 0) {
      line = word;
    } else if (line.length + 1 + word.length <= width) {
      line = line + " " + word;
    } else {
      lines.push(line);
      line = word;
    }
  }
  lines.push(line);
  return lines;
}
