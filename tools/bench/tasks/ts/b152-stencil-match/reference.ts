/** Vet a code against a stencil of digit, letter and wildcard slots. */
export function matchesStencil(stencil: string, code: string): boolean {
  if (typeof stencil !== "string" || stencil.length === 0) {
    throw new Error("matchesStencil expects a non-empty stencil string");
  }
  if (typeof code !== "string") {
    throw new Error("matchesStencil expects a string code");
  }
  if (code.length !== stencil.length) {
    return false;
  }
  for (let i = 0; i < stencil.length; i++) {
    const want = stencil[i];
    const have = code[i];
    if (want === "#" && !(have >= "0" && have <= "9")) return false;
    if (want === "@" && !/^[a-zA-Z]$/.test(have)) return false;
    if (want !== "#" && want !== "@" && want !== "?" && have !== want) return false;
  }
  return true;
}
