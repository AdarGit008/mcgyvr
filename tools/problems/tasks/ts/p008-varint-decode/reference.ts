export function decodeVarints(data: number[]): number[] {
  if (!Array.isArray(data)) {
    throw new Error("decodeVarints expects a list of byte values");
  }
  const values: number[] = [];
  let value = 0;
  let scale = 1;
  let length = 0;
  for (const byte of data) {
    if (!Number.isInteger(byte) || byte < 0 || byte > 255) {
      throw new Error("byte values must be integers in 0..255");
    }
    value += (byte & 0x7f) * scale;
    scale *= 128;
    length += 1;
    if (byte < 128) {
      if (length > 1 && byte === 0) {
        throw new Error("overlong varint encoding");
      }
      values.push(value);
      value = 0;
      scale = 1;
      length = 0;
    }
  }
  if (length > 0) {
    throw new Error("truncated varint");
  }
  return values;
}
