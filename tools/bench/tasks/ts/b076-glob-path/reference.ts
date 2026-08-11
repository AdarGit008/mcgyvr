export function globPath(pattern: string, path: string): boolean {
  if (typeof pattern !== "string" || typeof path !== "string") {
    throw new Error("globPath expects two strings");
  }
  if (pattern.length === 0 || path.length === 0) {
    throw new Error("empty pattern or path");
  }
  const step = (p: number, s: number): boolean => {
    if (p === pattern.length) return s === path.length;
    const ch = pattern[p];
    if (ch === "*") {
      if (step(p + 1, s)) return true;
      return s < path.length && path[s] !== "/" && step(p, s + 1);
    }
    if (s === path.length) return false;
    if (ch === "?") return path[s] !== "/" && step(p + 1, s + 1);
    return path[s] === ch && step(p + 1, s + 1);
  };
  return step(0, 0);
}
