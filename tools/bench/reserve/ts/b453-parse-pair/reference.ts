export function splitOnce(line: string): string[] {
  const cut = line.indexOf(":");
  if (cut === -1) {
    throw new Error("a pair needs a colon");
  }
  return [line.slice(0, cut), line.slice(cut + 1)];
}

export function parsePair(line: string): string[] {
  const parts = splitOnce(line);
  return [parts[0].trim(), parts[1].trim()];
}
