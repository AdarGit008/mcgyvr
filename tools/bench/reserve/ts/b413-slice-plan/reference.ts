export function sliceEnd(
  start: number,
  width: number,
  total: number,
): number {
  const end = start + width;
  return end > total ? total : end;
}

export function slicePlan(total: number, width: number): number[][] {
  const plan: number[][] = [];
  for (let start = 0; start < total; start += width) {
    plan.push([start, sliceEnd(start, width, total)]);
  }
  return plan;
}
