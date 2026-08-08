export function restoreFrontShift(alphabet: string, codes: number[]): string {
  if (typeof alphabet !== "string") {
    throw new Error("the alphabet must be a string");
  }
  if (alphabet.length === 0) {
    throw new Error("the alphabet must not be empty");
  }
  const ring = Array.from(alphabet);
  if (new Set(ring).size !== ring.length) {
    throw new Error("the alphabet carries one character twice");
  }
  if (!Array.isArray(codes)) {
    throw new Error("the codes must be a list");
  }
  let text = "";
  for (const code of codes) {
    if (typeof code !== "number" || !Number.isInteger(code)) {
      throw new Error("every code must be a whole number");
    }
    if (code < 0 || code >= ring.length) {
      throw new Error("the code names no slot of the ring");
    }
    const character = ring[code];
    text += character;
    ring.splice(code, 1);
    ring.unshift(character);
  }
  return text;
}
