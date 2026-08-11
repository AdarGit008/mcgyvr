export function unpackFrame(bytes: number[]): number[] {
  if (!Array.isArray(bytes)) {
    throw new Error("bytes must be a list");
  }
  for (const byte of bytes) {
    if (!Number.isInteger(byte) || byte < 0 || byte > 255) {
      throw new Error("bytes must be integers 0..255");
    }
  }
  let at = 0;
  function takeVarint(): number {
    let value = 0;
    let place = 1;
    let length = 0;
    for (;;) {
      if (at >= bytes.length) {
        throw new Error("the frame ends inside a varint");
      }
      const byte = bytes[at];
      at += 1;
      length += 1;
      if (length > 5) {
        throw new Error("a varint holds at most five bytes");
      }
      const group = byte & 127;
      if (byte >= 128) {
        value += group * place;
        place *= 128;
        continue;
      }
      if (length > 1 && group === 0) {
        throw new Error("a varint must not waste its final byte");
      }
      return value + group * place;
    }
  }
  const declared = takeVarint();
  const readings: number[] = [];
  for (let i = 0; i < declared; i += 1) {
    readings.push(takeVarint());
  }
  if (at > bytes.length - 1) {
    throw new Error("the frame ends before its trailer");
  }
  if (at < bytes.length - 1) {
    throw new Error("bytes left over after the trailer");
  }
  let sum = 0;
  for (let i = 0; i < bytes.length - 1; i += 1) {
    sum = (sum + bytes[i]) % 256;
  }
  if (bytes[at] !== sum) {
    throw new Error("the trailer does not equal the byte sum");
  }
  return readings;
}
