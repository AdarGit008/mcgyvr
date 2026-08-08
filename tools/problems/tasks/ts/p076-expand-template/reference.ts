export function expandTemplate(
  template: string,
  context: Record<string, unknown>,
  missing: string
): string {
  if (missing !== "error" && missing !== "keep" && missing !== "blank") {
    throw new Error("unknown policy: " + missing);
  }
  let out = "";
  let i = 0;
  while (i < template.length) {
    const ch = template[i];
    if (ch !== "$") {
      out += ch;
      i += 1;
      continue;
    }
    const next = template[i + 1];
    if (next === "$") {
      out += "$";
      i += 2;
      continue;
    }
    if (next !== "{") {
      throw new Error("stray dollar sign");
    }
    const close = template.indexOf("}", i + 2);
    if (close === -1) {
      throw new Error("unclosed placeholder");
    }
    const raw = template.slice(i + 2, close);
    const segments = raw.split(".");
    if (segments.some((segment) => segment === "")) {
      throw new Error("bad path: " + raw);
    }
    let value: unknown = context;
    let found = true;
    for (const segment of segments) {
      const isMap =
        value !== null && typeof value === "object" && !Array.isArray(value);
      if (isMap && segment in (value as Record<string, unknown>)) {
        value = (value as Record<string, unknown>)[segment];
      } else {
        found = false;
        break;
      }
    }
    if (!found) {
      if (missing === "error") {
        throw new Error("missing path: " + raw);
      }
      if (missing === "keep") {
        out += template.slice(i, close + 1);
      }
    } else if (typeof value === "string") {
      out += value;
    } else if (typeof value === "number" && Number.isInteger(value)) {
      out += String(value);
    } else {
      throw new Error("value at " + raw + " is not printable");
    }
    i = close + 1;
  }
  return out;
}
