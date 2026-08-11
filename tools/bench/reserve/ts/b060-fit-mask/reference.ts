/** Fit a text to a form input mask: A takes a letter, 9 a digit, else literal. */
export function fitMask(mask: string, text: string): string {
  if (typeof mask !== "string" || mask.length === 0) {
    throw new Error("mask must be a non-empty string");
  }
  if (typeof text !== "string") {
    throw new Error("text must be a string");
  }
  if (text.length !== mask.length) {
    throw new Error("text length must equal mask length");
  }
  let fitted = "";
  for (let i = 0; i < mask.length; i++) {
    const ch = mask[i];
    const c = text[i];
    if (ch === "A" && /[A-Za-z]/.test(c)) {
      fitted += c.toUpperCase();
    } else if (ch === "9" && /[0-9]/.test(c)) {
      fitted += c;
    } else if (ch !== "A" && ch !== "9" && c === ch) {
      fitted += c;
    } else {
      throw new Error("slot " + ch + " cannot take " + c);
    }
  }
  return fitted;
}
