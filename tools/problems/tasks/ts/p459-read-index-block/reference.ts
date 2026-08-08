function allowed(byte: number): boolean {
  return (byte >= 97 && byte <= 122) || (byte >= 48 && byte <= 57);
}

export function readIndexBlock(bytes: any): (string | number)[][] {
  if (!Array.isArray(bytes)) {
    throw new Error("bytes must be a list");
  }
  for (const byte of bytes) {
    if (typeof byte !== "number" || !Number.isInteger(byte) || byte < 0 || byte > 255) {
      throw new Error("every byte must be a whole number from 0 through 255");
    }
  }
  if (bytes.length === 0) {
    throw new Error("the block is empty, so it does not even carry its count");
  }

  const count = bytes[0];
  const rows: (string | number)[][] = [];
  let at = 1;
  let previous = "";
  for (let i = 0; i < count; i++) {
    if (at >= bytes.length) {
      throw new Error("the block ends where another entry was promised");
    }
    const width = bytes[at];
    if (width < 1) {
      throw new Error("an entry name must be at least one byte long");
    }
    if (at + 1 + width + 4 > bytes.length) {
      throw new Error("the block ends inside an entry");
    }
    let name = "";
    for (let k = 0; k < width; k++) {
      const byte = bytes[at + 1 + k];
      if (!allowed(byte)) {
        throw new Error("an entry name may hold only small letters and digits");
      }
      name += String.fromCharCode(byte);
    }
    if (name <= previous) {
      throw new Error("the entries are not in strictly rising name order");
    }
    previous = name;
    const base = at + 1 + width;
    rows.push([name, bytes[base] * 256 + bytes[base + 1], bytes[base + 2] * 256 + bytes[base + 3]]);
    at = base + 4;
  }
  if (at !== bytes.length) {
    throw new Error("the block carries bytes past its last entry");
  }
  return rows;
}
