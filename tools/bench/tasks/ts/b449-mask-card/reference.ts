export function lastFour(number: string): string {
  if (number.length <= 4) {
    return number;
  }
  return number.slice(number.length - 4);
}

export function maskCard(number: string): string {
  const shown = lastFour(number);
  return "*".repeat(number.length - shown.length) + shown;
}
