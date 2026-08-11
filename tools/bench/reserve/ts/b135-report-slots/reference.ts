/** Fixed-point rendering and the report slots that lay the numbers out. */

export function formatFixed(value: number, decimals: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error("value must be a finite number");
  }
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 6) {
    throw new Error("decimals must be an integer from 0 to 6");
  }
  const scale = 10 ** decimals;
  const scaled = Math.floor(Math.abs(value) * scale + 0.5);
  const whole = Math.floor(scaled / scale);
  const sign = value < 0 && scaled > 0 ? "-" : "";
  if (decimals === 0) {
    return sign + String(whole);
  }
  const fraction = String(scaled % scale).padStart(decimals, "0");
  return `${sign}${whole}.${fraction}`;
}

export function fillReport(
  template: string,
  values: Record<string, number>,
): string {
  if (typeof template !== "string") {
    throw new Error("template must be a string");
  }
  let out = "";
  let at = 0;
  while (at < template.length) {
    const ch = template[at];
    if (ch !== "[") {
      out += ch;
      at += 1;
      continue;
    }
    const close = template.indexOf("]", at + 1);
    if (close < 0) {
      throw new Error("slot never closed");
    }
    const parts = template.slice(at + 1, close).split(":");
    if (parts.length !== 3) {
      throw new Error("a slot is name:width:decimals");
    }
    const [name, widthText, decimalsText] = parts;
    if (!/^[A-Za-z_]+$/.test(name)) {
      throw new Error(`malformed slot name: ${name}`);
    }
    if (!/^\d+$/.test(widthText) || Number(widthText) < 1) {
      throw new Error("width must be a positive integer");
    }
    if (!/^\d+$/.test(decimalsText)) {
      throw new Error("decimals must be digits");
    }
    if (!(name in values)) {
      throw new Error(`no value for slot: ${name}`);
    }
    const rendered = formatFixed(values[name], Number(decimalsText));
    const width = Number(widthText);
    out += rendered.length >= width ? rendered : rendered.padStart(width, " ");
    at = close + 1;
  }
  return out;
}
