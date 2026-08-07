export function windowQuota(
  limit: number,
  width: number,
  calls: (string | number)[][]
): string[] {
  if (!Number.isInteger(limit) || limit <= 0) {
    throw new Error("limit must be a positive integer");
  }
  if (!Number.isInteger(width) || width <= 0) {
    throw new Error("width must be a positive integer");
  }
  let served = new Map<string, number>();
  let currentFrame = -1;
  let previous = -1;
  const labels: string[] = [];
  for (const call of calls) {
    const time = call[0];
    const name = call[1];
    if (typeof time !== "number" || !Number.isInteger(time) || time < 0) {
      throw new Error("time must be a non-negative integer");
    }
    if (previous >= 0 && time < previous) {
      throw new Error("times must not decrease");
    }
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("name must be a non-empty string");
    }
    previous = time;
    const frame = Math.floor(time / width);
    if (frame !== currentFrame) {
      served = new Map();
      currentFrame = frame;
    }
    const used = served.get(name) ?? 0;
    if (used < limit) {
      labels.push("ok");
      served.set(name, used + 1);
    } else {
      labels.push("over");
    }
  }
  return labels;
}
