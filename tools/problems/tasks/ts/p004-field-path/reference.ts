const IDENT = "[A-Za-z_][A-Za-z0-9_]*";
const INDEX = "\\[(?:0|[1-9][0-9]*)\\]";
const PATH = new RegExp(`^${IDENT}(?:${INDEX})*(?:\\.${IDENT}(?:${INDEX})*)*$`);

export function splitFieldPath(path: string): (string | number)[] {
  if (typeof path !== "string") {
    throw new Error("splitFieldPath expects a string");
  }
  if (!PATH.test(path)) {
    throw new Error("malformed field path");
  }
  const parts: (string | number)[] = [];
  for (const match of path.matchAll(/([A-Za-z_][A-Za-z0-9_]*)|\[([0-9]+)\]/g)) {
    if (match[1] !== undefined) {
      parts.push(match[1]);
    } else {
      parts.push(Number(match[2]));
    }
  }
  return parts;
}
