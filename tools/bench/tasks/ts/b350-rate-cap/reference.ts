export function rateCap(price: number, rate: number, most: number): number {
  let rise = Math.floor((price * rate) / 100);
  if (rise > most) {
    rise = most;
  }
  return price + rise;
}
