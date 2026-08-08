export function normalizeHostname(hostname: string): string {
  if (typeof hostname !== "string") {
    throw new Error("normalizeHostname expects a string");
  }
  let name = hostname.toLowerCase();
  if (name.endsWith(".")) {
    name = name.slice(0, -1);
  }
  if (name.length === 0 || name.length > 253) {
    throw new Error("hostname length is out of range");
  }
  for (const label of name.split(".")) {
    if (label.length < 1 || label.length > 63) {
      throw new Error("label length is out of range");
    }
    if (!/^[a-z0-9-]+$/.test(label)) {
      throw new Error("label has an invalid character");
    }
    if (label.startsWith("-") || label.endsWith("-")) {
      throw new Error("label may not start or end with a hyphen");
    }
  }
  return name;
}
