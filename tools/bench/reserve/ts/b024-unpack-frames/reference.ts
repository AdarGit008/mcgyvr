/** Decode a framed wire string: length-prefixed frames, then a count trailer. */

function scanDigits(stream: string, start: number): [string, number] {
  let cursor = start;
  while (
    cursor < stream.length &&
    stream[cursor] >= "0" &&
    stream[cursor] <= "9"
  ) {
    cursor += 1;
  }
  return [stream.slice(start, cursor), cursor];
}

export function unpackFrames(stream: string): string[] {
  if (typeof stream !== "string") {
    throw new Error("stream must be a string");
  }
  const frames: string[] = [];
  let cursor = 0;
  while (cursor < stream.length && stream[cursor] !== "#") {
    const [digits, afterDigits] = scanDigits(stream, cursor);
    cursor = afterDigits;
    if (digits.length === 0) {
      throw new Error("frame length is missing");
    }
    if (digits.length > 1 && digits[0] === "0") {
      throw new Error("frame length has a leading zero");
    }
    if (cursor >= stream.length || stream[cursor] !== ":") {
      throw new Error("expected ':' after the frame length");
    }
    cursor += 1;
    const length = Number(digits);
    if (cursor + length > stream.length) {
      throw new Error("frame payload is truncated");
    }
    frames.push(stream.slice(cursor, cursor + length));
    cursor += length;
    if (cursor >= stream.length || stream[cursor] !== ";") {
      throw new Error("frame is not terminated");
    }
    cursor += 1;
  }
  if (cursor >= stream.length || stream[cursor] !== "#") {
    throw new Error("count trailer is missing");
  }
  cursor += 1;
  const [countDigits, afterCount] = scanDigits(stream, cursor);
  cursor = afterCount;
  if (countDigits.length === 0) {
    throw new Error("trailer count is missing");
  }
  if (countDigits.length > 1 && countDigits[0] === "0") {
    throw new Error("trailer count has a leading zero");
  }
  if (cursor >= stream.length || stream[cursor] !== ";") {
    throw new Error("trailer is not terminated");
  }
  cursor += 1;
  if (cursor !== stream.length) {
    throw new Error("trailing garbage after the trailer");
  }
  if (Number(countDigits) !== frames.length) {
    throw new Error("trailer count does not match the frames");
  }
  return frames;
}
