export function tagCount(line: string): number {
  let count = 0;
  let open = false;
  for (const ch of line) {
    if (ch === "<") {
      open = true;
    } else if (ch === ">") {
      if (!open) {
        throw new Error("a closing bracket with nothing open");
      }
      open = false;
      count += 1;
    }
  }
  return count;
}
