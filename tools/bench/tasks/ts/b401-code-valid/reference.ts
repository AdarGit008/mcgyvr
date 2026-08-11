export function codeValid(code: string, length: number): boolean {
  if (length <= 0) {
    throw new Error("length must be positive");
  }
  if (code.length !== length) {
    return false;
  }
  return /^[A-Z0-9]+$/.test(code);
}
