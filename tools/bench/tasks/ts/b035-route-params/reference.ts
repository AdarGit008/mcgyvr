/** Route patterns over slash-separated paths: literals, :name, * and **. */
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function splitSegments(path: string): string[] {
  if (typeof path !== "string" || path.length === 0) {
    throw new Error("path must be a non-empty string");
  }
  if (path[0] !== "/") {
    throw new Error("path must start with a slash");
  }
  if (path === "/") {
    return [];
  }
  const segments = path.slice(1).split("/");
  for (const segment of segments) {
    if (segment.length === 0) {
      throw new Error("path holds an empty segment");
    }
  }
  return segments;
}

function matchFrom(
  pattern: string[],
  pi: number,
  segments: string[],
  si: number,
  captures: Record<string, string>,
): boolean {
  if (pi === pattern.length) {
    return si === segments.length;
  }
  const token = pattern[pi];
  if (token === "**") {
    for (let take = 0; si + take <= segments.length; take++) {
      if (matchFrom(pattern, pi + 1, segments, si + take, captures)) {
        return true;
      }
    }
    return false;
  }
  if (si === segments.length) {
    return false;
  }
  if (token.startsWith(":")) {
    captures[token.slice(1)] = segments[si];
    return matchFrom(pattern, pi + 1, segments, si + 1, captures);
  }
  if (token !== "*" && token !== segments[si]) {
    return false;
  }
  return matchFrom(pattern, pi + 1, segments, si + 1, captures);
}

export function matchRoute(
  pattern: string,
  path: string,
): Record<string, string> | null {
  const tokens = splitSegments(pattern);
  const names = new Set<string>();
  let rests = 0;
  for (const token of tokens) {
    if (token === "**") {
      rests += 1;
      if (rests > 1) {
        throw new Error("** may appear at most once");
      }
    } else if (token.startsWith(":")) {
      const name = token.slice(1);
      if (!NAME_RE.test(name)) {
        throw new Error("malformed capture name: " + token);
      }
      if (names.has(name)) {
        throw new Error("repeated capture name: " + name);
      }
      names.add(name);
    }
  }
  const segments = splitSegments(path);
  const captures: Record<string, string> = {};
  return matchFrom(tokens, 0, segments, 0, captures) ? captures : null;
}

export function firstRoute(patterns: string[], path: string): number {
  for (let index = 0; index < patterns.length; index++) {
    if (matchRoute(patterns[index], path) !== null) {
      return index;
    }
  }
  return -1;
}
