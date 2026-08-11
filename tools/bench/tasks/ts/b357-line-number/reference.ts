export function lineNumber(block: string): string {
  if (block === "") {
    return "";
  }
  const out: string[] = [];
  const lines = block.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    out.push(String(i + 1) + ": " + lines[i]);
  }
  return out.join("\n");
}
