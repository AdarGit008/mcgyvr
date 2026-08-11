export function pluralOf(noun: string): string {
  if (/(s|x|ch|sh)$/.test(noun)) {
    return noun + "es";
  }
  if (/[^aeiou]y$/.test(noun)) {
    return noun.slice(0, -1) + "ies";
  }
  return noun + "s";
}
