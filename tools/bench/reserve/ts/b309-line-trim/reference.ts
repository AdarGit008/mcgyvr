export function lineTrim(block: string): string {
  const trimmed: string[] = [];
  for (const line of block.split("\n")) {
    trimmed.push(line.replace(/ +$/, ""));
  }
  return trimmed.join("\n");
}
