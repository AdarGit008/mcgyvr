export function wrapText(text: string, width: number): string[] {
  if (typeof text !== "string") {
    throw new Error("wrapText expects a string");
  }
  if (typeof width !== "number" || !Number.isInteger(width) || width < 1) {
    throw new Error("width must be a positive integer");
  }
  if (/^ | $| {2}/.test(text)) {
    throw new Error("text must use single spaces between words");
  }
  const lines: string[] = [];
  let current = "";
  for (const word of text.split(" ")) {
    if (current === "") {
      current = word;
    } else if (current.length + 1 + word.length <= width) {
      current += " " + word;
    } else {
      lines.push(current);
      current = word;
    }
  }
  if (current !== "") {
    lines.push(current);
  }
  return lines;
}
