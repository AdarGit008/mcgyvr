export function fillPlaceholders(
  text: string,
  slots: Record<string, string>
): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch !== "%") {
      out += ch;
      i += 1;
      continue;
    }
    if (text[i + 1] === "%") {
      out += "%";
      i += 2;
      continue;
    }
    const close = text.indexOf("%", i + 1);
    if (close === -1) {
      throw new Error("unpaired percent sign");
    }
    const name = text.slice(i + 1, close);
    if (!(name in slots)) {
      throw new Error("unknown slot: " + name);
    }
    out += slots[name];
    i = close + 1;
  }
  return out;
}
