export function cloudCode(
  table: Record<string, string>,
  code: string,
): string {
  const key = code.toUpperCase();
  if (Object.prototype.hasOwnProperty.call(table, key)) {
    return table[key];
  }
  return "unknown";
}
