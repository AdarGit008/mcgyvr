const FACTORS: Record<string, number> = {
  B: 1,
  KiB: 1024,
  MiB: 1024 * 1024,
  GiB: 1024 * 1024 * 1024,
};

export function parseByteSize(input: string): number {
  if (typeof input !== "string" || input.length === 0) {
    throw new Error("parseByteSize expects a non-empty string");
  }
  const match = /^(\d+)([A-Za-z]+)$/.exec(input);
  if (match === null) {
    throw new Error("malformed size: " + input);
  }
  const unit = match[2];
  if (!(unit in FACTORS)) {
    throw new Error("unknown unit: " + unit);
  }
  return Number(match[1]) * FACTORS[unit];
}
