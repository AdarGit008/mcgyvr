export function slotIn(ordered: number[], value: number): number[] {
  const out: number[] = [];
  let placed = false;
  for (const item of ordered) {
    if (!placed && value < item) {
      out.push(value);
      placed = true;
    }
    out.push(item);
  }
  if (!placed) {
    out.push(value);
  }
  return out;
}
