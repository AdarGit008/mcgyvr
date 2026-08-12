/** Render a packed sixteen-bit settings word as named fields. */
export function describeWord(word: number, fields: [string, number][]): string {
  let total = 0;
  for (const [, width] of fields) {
    total += width;
  }
  if (total !== 16) {
    throw new Error("field widths must cover all sixteen bits");
  }
  const parts: string[] = [];
  let offset = 16;
  for (const [name, width] of fields) {
    offset -= width;
    const value = (word >> offset) & ((1 << width) - 1);
    if (width === 1) {
      parts.push(name + "=" + (value === 1 ? "on" : "off"));
    } else {
      parts.push(name + "=" + String(value));
    }
  }
  return parts.join(",");
}
