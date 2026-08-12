/** Centre a label on a banner board, the spare cell going right. */
export function centerBanner(label: string, width: number, fill: string): string {
  if (typeof label !== "string" || label.includes("\n")) {
    throw new Error("label must be a single-line string");
  }
  if (!Number.isInteger(width) || width < 1) {
    throw new Error("width must be a positive integer");
  }
  if (label.length > width) {
    throw new Error("label is wider than the board");
  }
  if (typeof fill !== "string" || fill.length !== 1) {
    throw new Error("fill must be a single character");
  }
  const spare = width - label.length;
  const left = Math.floor(spare / 2);
  return fill.repeat(left) + label + fill.repeat(spare - left);
}
