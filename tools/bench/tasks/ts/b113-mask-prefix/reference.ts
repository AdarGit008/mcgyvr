export function maskFromPrefix(prefix: number): string {
  if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
    throw new Error("prefix must be an integer from 0 to 32");
  }
  const octets: number[] = [];
  for (let slot = 0; slot < 4; slot += 1) {
    const ones = Math.min(8, Math.max(0, prefix - slot * 8));
    octets.push(256 - 2 ** (8 - ones));
  }
  return octets.join(".");
}

export function prefixFromMask(mask: string): number {
  if (typeof mask !== "string") {
    throw new Error("mask must be a string");
  }
  const fields = mask.split(".");
  if (fields.length !== 4) {
    throw new Error("a mask is four dot-separated octets");
  }
  let value = 0;
  for (const field of fields) {
    if (!/^[0-9]+$/.test(field)) {
      throw new Error("octet fields must be decimal digits");
    }
    if (field !== "0" && field.startsWith("0")) {
      throw new Error("octet fields must not carry leading zeros");
    }
    const octet = Number(field);
    if (octet > 255) {
      throw new Error("octets must lie from 0 to 255");
    }
    value = value * 256 + octet;
  }
  let ones = 0;
  let ended = false;
  for (let bit = 31; bit >= 0; bit -= 1) {
    const set = Math.floor(value / 2 ** bit) % 2 === 1;
    if (set && ended) {
      throw new Error("mask one bits must form one unbroken run");
    }
    if (set) {
      ones += 1;
    } else {
      ended = true;
    }
  }
  return ones;
}
