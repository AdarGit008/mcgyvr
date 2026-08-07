export function padMirroredMargins(
  readings: number[],
  left: number,
  right: number,
): number[] {
  if (!Array.isArray(readings) || readings.length === 0) {
    throw new Error("the run must be a non-empty list");
  }
  for (const reading of readings) {
    if (typeof reading !== "number" || !Number.isInteger(reading)) {
      throw new Error("every reading is a whole number");
    }
  }
  for (const width of [left, right]) {
    if (typeof width !== "number" || !Number.isInteger(width) || width < 0) {
      throw new Error("a margin width is a whole number at or above nought");
    }
  }
  const span = readings.length;
  const period = span * 2;
  const at = (index: number): number => {
    let folded = ((index % period) + period) % period;
    if (folded >= span) {
      folded = period - 1 - folded;
    }
    return readings[folded];
  };
  const padded: number[] = [];
  for (let index = -left; index < span + right; index++) {
    padded.push(at(index));
  }
  return padded;
}
