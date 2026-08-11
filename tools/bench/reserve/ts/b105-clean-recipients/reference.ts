/** Tidy a mailing list into canonical recipient addresses. */

export function cleanRecipients(raw: string[]): string[] {
  if (!Array.isArray(raw)) {
    throw new Error("recipients must arrive as a list");
  }
  const cleaned: string[] = [];
  const seen = new Set<string>();
  for (const entry of raw) {
    if (typeof entry !== "string") {
      throw new Error("each recipient must be a string");
    }
    let address = entry.trim();
    const opens = address.split("<").length - 1;
    const closes = address.split(">").length - 1;
    if (opens > 0 || closes > 0) {
      const open = address.indexOf("<");
      const close = address.indexOf(">");
      if (
        opens !== 1 ||
        closes !== 1 ||
        close !== address.length - 1 ||
        close <= open + 1
      ) {
        throw new Error("a display entry is text <address>");
      }
      address = address.slice(open + 1, close).trim();
    }
    if (/\s/.test(address)) {
      throw new Error("an address holds no inner whitespace");
    }
    const pieces = address.split("@");
    if (pieces.length !== 2) {
      throw new Error("an address holds exactly one @");
    }
    const local = pieces[0];
    const domain = pieces[1].toLowerCase();
    if (local.length === 0) {
      throw new Error("the local part must not be empty");
    }
    if (
      domain.length === 0 ||
      !domain.includes(".") ||
      domain.startsWith(".") ||
      domain.endsWith(".")
    ) {
      throw new Error("the domain needs inner dots");
    }
    const canonical = local + "@" + domain;
    const key = canonical.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      cleaned.push(canonical);
    }
  }
  return cleaned;
}
