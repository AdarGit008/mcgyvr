export function passCheck(phrase: string): boolean {
  if (phrase.length < 8) {
    return false;
  }
  return /[0-9]/.test(phrase) && /[a-zA-Z]/.test(phrase);
}
