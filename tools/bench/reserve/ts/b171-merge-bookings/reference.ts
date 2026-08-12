export function mergeBookings(plan: string): string {
  if (typeof plan !== "string" || plan === "") throw new Error("plan must be a non-empty string");
  const slots: number[][] = [];
  for (const part of plan.split(",")) {
    const ends = part.split("-");
    if (ends.length !== 2 || !ends.every((e) => /^\d+$/.test(e))) throw new Error("a slot reads start-end");
    const [start, end] = ends.map(Number);
    if (start >= end || end > 24) throw new Error("a slot must run forward inside the day");
    slots.push([start, end]);
  }
  slots.sort((a, b) => a[0] - b[0]);
  const merged: number[][] = [];
  for (const [start, end] of slots) {
    const last = merged[merged.length - 1];
    if (last !== undefined && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  return merged.map((slot) => `${slot[0]}-${slot[1]}`).join(",");
}
