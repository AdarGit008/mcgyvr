export function keepIndex(place: number, every: number): boolean {
  return place % every !== 0;
}

export function dropEvery(entries: string[], every: number): string[] {
  const kept: string[] = [];
  for (let i = 0; i < entries.length; i += 1) {
    if (keepIndex(i + 1, every)) {
      kept.push(entries[i]);
    }
  }
  return kept;
}
