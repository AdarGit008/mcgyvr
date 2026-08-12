/** A label with one surrounding pair of brackets removed. */
export function unwrapLabel(label: string): string {
  if (label.startsWith("[") && label.endsWith("]")) {
    return label.slice(1, -1);
  }
  return label;
}
