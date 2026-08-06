/** Backtracking matcher for the '. * ^ $' dialect with substring semantics. */
export function match(pattern: string, text: string): boolean {
  let p = pattern;
  let anchorStart = false;
  let anchorEnd = false;
  if (p[0] === "^") {
    anchorStart = true;
    p = p.slice(1);
  }
  if (p.length > 0 && p[p.length - 1] === "$") {
    anchorEnd = true;
    p = p.slice(0, -1);
  }
  for (let k = 0; k < p.length; k++) {
    if (p[k] === "*" && (k === 0 || p[k - 1] === "*")) {
      throw new Error("'*' must follow a literal character or '.'");
    }
  }
  const here = (pi: number, ti: number): boolean => {
    if (pi === p.length) {
      return anchorEnd ? ti === text.length : true;
    }
    const star = p[pi + 1] === "*";
    const first = ti < text.length && (p[pi] === "." || p[pi] === text[ti]);
    if (star) {
      if (here(pi + 2, ti)) return true;
      return first ? here(pi, ti + 1) : false;
    }
    return first ? here(pi + 1, ti + 1) : false;
  };
  if (anchorStart) return here(0, 0);
  for (let start = 0; start <= text.length; start++) {
    if (here(0, start)) return true;
  }
  return false;
}
