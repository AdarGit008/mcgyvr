export function moneyText(pence: number): string {
  const pounds = Math.floor(pence / 100);
  const rest = pence - pounds * 100;
  const shown = rest < 10 ? "0" + String(rest) : String(rest);
  return String(pounds) + "." + shown;
}
