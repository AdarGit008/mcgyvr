const ALLOWED = ["sku", "count", "note"];

export function checkManifest(line: Record<string, unknown>): Record<string, unknown> {
  if (Object.keys(line).some((key) => !ALLOWED.includes(key))) {
    throw new Error("a manifest line carries sku, count and note only");
  }
  const sku = line.sku;
  const count = line.count;
  const note = line.note === undefined ? "" : line.note;
  if (typeof sku !== "string" || sku.trim() === "") {
    throw new Error("the sku must be a non-empty string");
  }
  if (typeof count !== "number" || !Number.isInteger(count) || count < 1) {
    throw new Error("the count must be a positive whole number");
  }
  if (typeof note !== "string") {
    throw new Error("the note must be a string");
  }
  return { sku: sku.trim().toUpperCase(), count, note };
}
