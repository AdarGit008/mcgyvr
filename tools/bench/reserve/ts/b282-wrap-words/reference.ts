export function wrapWords(sentence: string, width: number): string[] {
  const lines: string[] = [];
  let current = "";
  for (const word of sentence.split(/\s+/).filter((w) => w !== "")) {
    const joined = current === "" ? word : current + " " + word;
    if (current !== "" && joined.length > width) {
      lines.push(current);
      current = word;
    } else {
      current = joined;
    }
  }
  if (current !== "") {
    lines.push(current);
  }
  return lines;
}
