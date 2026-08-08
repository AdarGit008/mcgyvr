export function packFields(widths: number[], values: number[]): number {
  if (!Array.isArray(widths) || !Array.isArray(values)) {
    throw new Error("packFields expects two lists");
  }
  if (widths.length !== values.length) {
    throw new Error("widths and values must have the same length");
  }
  if (widths.length === 0) {
    throw new Error("at least one field is required");
  }
  let totalWidth = 0;
  for (const width of widths) {
    if (!Number.isInteger(width) || width < 1) {
      throw new Error("each width must be a positive integer");
    }
    totalWidth += width;
  }
  if (totalWidth > 30) {
    throw new Error("combined width must not exceed 30 bits");
  }
  let packed = 0;
  for (let i = 0; i < widths.length; i++) {
    const value = values[i];
    if (!Number.isInteger(value) || value < 0) {
      throw new Error("each value must be a non-negative integer");
    }
    if (value >= 2 ** widths[i]) {
      throw new Error("value does not fit in its field width");
    }
    packed = packed * 2 ** widths[i] + value;
  }
  return packed;
}
