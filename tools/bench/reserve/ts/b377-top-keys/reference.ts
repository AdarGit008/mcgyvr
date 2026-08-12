export function topKeys(counts: Record<string, number>): string[] {
  const names = Object.keys(counts);
  if (names.length === 0) {
    return [];
  }
  let best = counts[names[0]];
  for (const name of names) {
    if (counts[name] > best) {
      best = counts[name];
    }
  }
  return names.filter((name) => counts[name] === best).sort();
}
