export function admitBytes(
  perKey: number,
  total: number,
  span: number,
  entries: (string | number)[][]
): string[] {
  for (const limit of [perKey, total, span]) {
    if (!Number.isInteger(limit) || limit <= 0) {
      throw new Error("perKey, total and span must be positive integers");
    }
  }
  const carried: [number, string, number][] = [];
  const labels: string[] = [];
  let previous = -1;
  for (const entry of entries) {
    const time = entry[0];
    const key = entry[1];
    const size = entry[2];
    if (typeof time !== "number" || !Number.isInteger(time) || time < 0) {
      throw new Error("time must be a non-negative integer");
    }
    if (previous >= 0 && time < previous) {
      throw new Error("times must never decrease");
    }
    if (typeof key !== "string" || key.length === 0) {
      throw new Error("key must be a non-empty string");
    }
    if (typeof size !== "number" || !Number.isInteger(size) || size <= 0) {
      throw new Error("size must be a positive integer");
    }
    previous = time;
    let keyVolume = 0;
    let allVolume = 0;
    for (const [when, who, howMuch] of carried) {
      if (when > time - span) {
        allVolume += howMuch;
        if (who === key) {
          keyVolume += howMuch;
        }
      }
    }
    if (keyVolume + size <= perKey && allVolume + size <= total) {
      labels.push("pass");
      carried.push([time, key, size]);
    } else {
      labels.push("drop");
    }
  }
  return labels;
}
