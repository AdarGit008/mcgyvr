export function tokenFold(phrase: string): string {
  const words = phrase.split(/\s+/).filter((word) => word.length > 0);
  const folded = words.map(
    (word) => word[0].toUpperCase() + word.slice(1).toLowerCase(),
  );
  return folded.join(" ");
}
