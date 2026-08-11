export function rowKey(name: string): string {
  return name[0].toUpperCase();
}

export function indexRows(names: string[]): Record<string, string[]> {
  const index: Record<string, string[]> = {};
  for (const name of names) {
    const key = rowKey(name);
    if (!(key in index)) {
      index[key] = [];
    }
    index[key].push(name);
  }
  return index;
}
