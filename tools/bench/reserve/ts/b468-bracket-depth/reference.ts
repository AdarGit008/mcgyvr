export function bracketDepth(text: string): number {
  let open = 0;
  let deepest = 0;
  for (const ch of text) {
    if (ch === "(") {
      open += 1;
      if (open > deepest) {
        deepest = open;
      }
    } else if (ch === ")") {
      if (open === 0) {
        throw new Error("a bracket closes before it opens");
      }
      open -= 1;
    }
  }
  if (open !== 0) {
    throw new Error("a bracket is left open");
  }
  return deepest;
}
