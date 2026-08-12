export function blotMask(code: string): string {
  if (code.length <= 4) {
    return code;
  }
  return "*".repeat(code.length - 4) + code.slice(-4);
}
