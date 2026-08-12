export function tallyBar(count: number, width: number): string {
  if (count <= width) {
    return "#".repeat(count);
  }
  return "#".repeat(width - 1) + ">";
}
