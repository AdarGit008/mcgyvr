export function durHours(minutes: number): number {
  return Math.floor(minutes / 60);
}

export function durText(minutes: number): string {
  const hours = durHours(minutes);
  const rest = minutes - hours * 60;
  if (hours > 0 && rest > 0) {
    return String(hours) + "h" + String(rest) + "m";
  }
  if (hours > 0) {
    return String(hours) + "h";
  }
  return String(rest) + "m";
}
