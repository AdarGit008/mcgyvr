export function tidyPath(path: string): string {
  if (typeof path !== "string" || path === "") {
    throw new Error("path must be a non-empty string");
  }
  const kept: string[] = [];
  for (const segment of path.split("/")) {
    if (segment === "") {
      throw new Error("empty segment in path");
    }
    if (segment === "..") {
      if (kept.length === 0) {
        throw new Error("path climbs above its start");
      }
      kept.pop();
    } else if (segment !== ".") {
      kept.push(segment);
    }
  }
  return kept.length === 0 ? "." : kept.join("/");
}
