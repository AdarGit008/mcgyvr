export function decodeFrames(stream: number[]): number[][] {
  if (!Array.isArray(stream)) {
    throw new Error("decodeFrames expects a list of bytes");
  }
  for (const byte of stream) {
    if (!Number.isInteger(byte) || byte < 0 || byte > 255) {
      throw new Error(`not a byte: ${byte}`);
    }
  }
  const frames: number[][] = [];
  let i = 0;
  while (i < stream.length) {
    if (i + 2 > stream.length) {
      throw new Error("stream ends inside a header");
    }
    const length = stream[i] * 256 + stream[i + 1];
    i += 2;
    if (i + length + 1 > stream.length) {
      throw new Error("stream ends inside a frame");
    }
    const payload = stream.slice(i, i + length);
    i += length;
    let check = 0;
    for (const byte of payload) {
      check ^= byte;
    }
    if (stream[i] !== check) {
      throw new Error("trailing byte disagrees with payload");
    }
    i += 1;
    frames.push(payload);
  }
  return frames;
}
