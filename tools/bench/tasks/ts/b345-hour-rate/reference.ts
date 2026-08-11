export function hourRate(rate: number): number {
  return rate;
}

/** Pay for a week, with overtime beyond forty hours. */
export function weekPay(hours: number, rate: number): number {
  if (hours <= 40) {
    return hours * hourRate(rate);
  }
  const extra = hours - 40;
  return 40 * hourRate(rate) + Math.floor((extra * hourRate(rate) * 3) / 2);
}
