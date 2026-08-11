export function siftMarks(entries: string[], mark: string): string[][] {
  const carrying: string[] = [];
  const plain: string[] = [];
  for (const entry of entries) {
    if (entry.startsWith(mark)) {
      carrying.push(entry);
    } else {
      plain.push(entry);
    }
  }
  return [carrying, plain];
}
