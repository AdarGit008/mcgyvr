export function flagList(line: string): string[] {
  const flags: string[] = [];
  for (const word of line.split(" ")) {
    if (word.startsWith("-")) {
      flags.push(word.slice(1));
    }
  }
  return flags;
}
