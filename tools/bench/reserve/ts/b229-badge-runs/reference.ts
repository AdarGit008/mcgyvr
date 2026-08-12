export function badgeRuns(badges: string): string {
  if (badges.length === 0) {
    throw new Error("no badges to compress");
  }
  let out = "";
  let start = 0;
  for (let i = 1; i <= badges.length; i += 1) {
    if (i === badges.length || badges[i] !== badges[start]) {
      out += badges[start] + String(i - start);
      start = i;
    }
  }
  return out;
}
