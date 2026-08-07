function checkSlot(key: string): void {
  if (!/^\d+$/.test(key)) {
    throw new Error("slot number must be digits: " + key);
  }
  if (key.length > 1 && key[0] === "0") {
    throw new Error("slot number carries a padding zero");
  }
  if (Number(key) === 0) {
    throw new Error("slot number is zero");
  }
}

function settle(body: string, slots: Map<string, string>): string {
  let out = "";
  let at = 0;
  while (at < body.length) {
    const ch = body[at];
    if (ch === "{") {
      if (body[at + 1] === "{") {
        out += "{";
        at += 2;
        continue;
      }
      const close = body.indexOf("}", at + 1);
      if (close === -1) {
        throw new Error("brace opened and never closed");
      }
      const key = body.slice(at + 1, close);
      checkSlot(key);
      const stored = slots.get(key);
      if (stored === undefined) {
        throw new Error("splice names a slot not stored yet");
      }
      out += stored;
      at = close + 1;
      continue;
    }
    if (ch === "}") {
      if (body[at + 1] === "}") {
        out += "}";
        at += 2;
        continue;
      }
      throw new Error("closing brace with nothing open");
    }
    out += ch;
    at += 1;
  }
  return out;
}

export function expandGlossary(script: string[]): string {
  if (!Array.isArray(script)) {
    throw new Error("script must be a list");
  }
  const slots = new Map<string, string>();
  const sent: string[] = [];
  for (const line of script) {
    if (typeof line !== "string") {
      throw new Error("every line must be a string");
    }
    if (line.startsWith("!")) {
      const key = line.slice(1);
      checkSlot(key);
      const stored = slots.get(key);
      if (stored === undefined) {
        throw new Error("send line names a slot never stored");
      }
      sent.push(stored);
      continue;
    }
    const cut = line.indexOf("=");
    if (cut === -1) {
      throw new Error("line is of neither kind");
    }
    const key = line.slice(0, cut);
    checkSlot(key);
    if (slots.has(key)) {
      throw new Error("slot stored a second time");
    }
    slots.set(key, settle(line.slice(cut + 1), slots));
  }
  return sent.join("");
}
