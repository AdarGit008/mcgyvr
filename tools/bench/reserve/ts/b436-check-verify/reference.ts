export function checkVerify(code: string): boolean {
  let total = 0;
  for (const ch of code) {
    total += Number(ch);
  }
  return total % 10 === 0;
}
