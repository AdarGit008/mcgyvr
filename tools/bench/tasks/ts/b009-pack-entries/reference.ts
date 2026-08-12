/** Serialize [key, value] string pairs into one escaped line. */

export function packEntries(entries: [string, string][]): string {
  if (!Array.isArray(entries)) {
    throw new Error("entries must be a list of pairs");
  }
  const escape = (text: string): string => {
    let out = "";
    for (const ch of text) {
      out += ch === "\\" || ch === "=" || ch === ";" ? "\\" + ch : ch;
    }
    return out;
  };
  const seen: Set<string> = new Set();
  const rendered: string[] = [];
  for (const entry of entries) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("each entry must be a [key, value] pair");
    }
    const [key, value] = entry;
    if (typeof key !== "string" || typeof value !== "string") {
      throw new Error("keys and values must be strings");
    }
    if (key === "") {
      throw new Error("keys must not be empty");
    }
    if (seen.has(key)) {
      throw new Error("keys must not repeat");
    }
    seen.add(key);
    rendered.push(escape(key) + "=" + escape(value));
  }
  return rendered.join(";");
}
