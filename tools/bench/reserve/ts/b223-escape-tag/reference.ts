const SAFE = /[A-Za-z0-9_-]/;

export function escapeTag(label: string): string {
  if (typeof label !== "string" || label.length === 0) {
    throw new Error("a label is a non-empty string");
  }
  let out = "";
  for (const ch of label) {
    const code = ch.charCodeAt(0);
    if (code > 127) {
      throw new Error("a label holds ASCII only");
    }
    out += SAFE.test(ch) ? ch : "%" + code.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}
