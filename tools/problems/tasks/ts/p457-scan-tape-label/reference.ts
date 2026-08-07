export function scanTapeLabel(
  bytes: any,
): { major: number; minor: number; records: number; extras: number[][] } {
  if (!Array.isArray(bytes)) {
    throw new Error("bytes must be a list");
  }
  for (const byte of bytes) {
    if (typeof byte !== "number" || !Number.isInteger(byte) || byte < 0 || byte > 255) {
      throw new Error("every byte must be a whole number from 0 through 255");
    }
  }
  if (bytes.length < 5) {
    throw new Error("the run is too short for the fixed part of the label");
  }
  if (bytes[0] !== 212 || bytes[1] !== 79) {
    throw new Error("the two opening bytes are not this label's marker");
  }
  const major = bytes[2];
  if (major !== 1 && major !== 2) {
    throw new Error(`major ${major} is not a shape this reader knows`);
  }
  const minor = bytes[3];
  if (minor < 1) {
    throw new Error("the record width must be at least one byte");
  }
  const records = bytes[4];

  let headerLength = 5;
  const extras: number[][] = [];
  if (major === 2) {
    if (bytes.length < 6) {
      throw new Error("the run ends before the extra count");
    }
    const count = bytes[5];
    headerLength = 6 + 3 * count;
    if (bytes.length < headerLength) {
      throw new Error("the run ends inside the extra table");
    }
    let last = -1;
    for (let i = 0; i < count; i++) {
      const at = 6 + 3 * i;
      const kind = bytes[at];
      if (kind <= last) {
        throw new Error("the extra table is not in rising order of kind");
      }
      last = kind;
      extras.push([kind, bytes[at + 1] * 256 + bytes[at + 2]]);
    }
  }

  if (bytes.length - headerLength !== records * minor) {
    throw new Error("what follows the label is not the run of records it promises");
  }
  return { major, minor, records, extras };
}
