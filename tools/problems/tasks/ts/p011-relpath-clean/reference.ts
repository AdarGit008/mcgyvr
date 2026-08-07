/** A cleaned form of a slash-separated relative path. */
export function normalizeRelPath(path: string): string {
  if (typeof path !== "string") {
    throw new Error("normalizeRelPath expects a string");
  }
  if (path === "") {
    throw new Error("empty path");
  }
  if (path.startsWith("/")) {
    throw new Error("path must be relative");
  }
  const out: string[] = [];
  for (const segment of path.split("/")) {
    if (segment === "" || segment === ".") {
      continue;
    }
    if (segment === "..") {
      if (out.length === 0) {
        throw new Error("path escapes above its starting point");
      }
      out.pop();
    } else {
      out.push(segment);
    }
  }
  return out.length > 0 ? out.join("/") : ".";
}
