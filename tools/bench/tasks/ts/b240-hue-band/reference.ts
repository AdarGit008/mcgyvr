export function hueBand(degrees: number): string {
  const hue = ((degrees % 360) + 360) % 360;
  if (hue < 60 || hue >= 300) {
    return "red";
  }
  return hue < 180 ? "green" : "blue";
}
