const ACCEPTED = [5, 10, 25, 100];

export function vendCredit(coins: number[], price: number): number {
  if (typeof price !== "number" || !Number.isInteger(price) || price < 1 || price % 5 !== 0) {
    throw new Error("a price is a positive whole number of cents in steps of five");
  }
  let credit = 0;
  for (const coin of coins) {
    if (!ACCEPTED.includes(coin)) {
      throw new Error(`the acceptor spits out ${coin}`);
    }
    credit += coin;
    while (credit >= price) {
      credit -= price;
    }
  }
  return credit;
}
