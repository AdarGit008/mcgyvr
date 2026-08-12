export function caseCount(text: string): number[] {
  let capitals = 0;
  let smalls = 0;
  for (const ch of text) {
    if (/^[A-Z]$/.test(ch)) {
      capitals += 1;
    } else if (/^[a-z]$/.test(ch)) {
      smalls += 1;
    }
  }
  return [capitals, smalls];
}
