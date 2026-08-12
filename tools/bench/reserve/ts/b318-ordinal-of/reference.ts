export function ordinalOf(value: number): string {
  const teens = [11, 12, 13];
  if (teens.includes(value % 100)) {
    return String(value) + "th";
  }
  const last = value % 10;
  if (last === 1) {
    return String(value) + "st";
  }
  if (last === 2) {
    return String(value) + "nd";
  }
  if (last === 3) {
    return String(value) + "rd";
  }
  return String(value) + "th";
}
