/** Normalize a user-typed label into its canonical hyphenated form. */

const RESERVED = ["new", "all", "none"];

export function normalizeLabel(raw: string): string {
  if (typeof raw !== "string") {
    throw new Error("label must be a string");
  }
  const trimmed = raw.trim();
  for (const ch of trimmed) {
    if (!/^[A-Za-z0-9 _-]$/.test(ch)) {
      throw new Error("label contains a forbidden character");
    }
  }
  let label = "";
  let pendingSeparator = false;
  for (const ch of trimmed.toLowerCase()) {
    if (ch === " " || ch === "_" || ch === "-") {
      pendingSeparator = label !== "";
      continue;
    }
    if (pendingSeparator) {
      label += "-";
      pendingSeparator = false;
    }
    label += ch;
  }
  if (label === "") {
    throw new Error("label is empty once normalized");
  }
  if (label.length > 32) {
    throw new Error("label is longer than 32 characters");
  }
  if (RESERVED.includes(label)) {
    throw new Error("label is a reserved name");
  }
  return label;
}
