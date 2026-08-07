function charged(balance: number, rate: number): number {
  return Math.floor((balance * rate + 5000) / 10000);
}

export function levelPaymentSchedule(
  opening: number,
  rate: number,
  payment: number,
  terms: number,
): number[][] {
  for (const value of [opening, rate, payment, terms]) {
    if (!Number.isInteger(value)) {
      throw new Error("opening, rate, payment and terms must be whole numbers");
    }
  }
  if (opening <= 0 || payment <= 0 || terms <= 0) {
    throw new Error("opening, payment and terms must be above zero");
  }
  if (rate < 0) {
    throw new Error("rate must not fall below zero");
  }
  if (payment <= charged(opening, rate)) {
    throw new Error("payment must exceed the first period's charge");
  }

  const rows: number[][] = [];
  let balance = opening;
  for (let period = 1; period <= terms; period++) {
    const charge = charged(balance, rate);
    if (period === terms || payment >= charge + balance) {
      rows.push([charge + balance, charge, balance, 0]);
      break;
    }
    const bite = payment - charge;
    balance -= bite;
    rows.push([payment, charge, bite, balance]);
  }
  return rows;
}
