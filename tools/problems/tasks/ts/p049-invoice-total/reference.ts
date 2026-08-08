function halfUp(amount: number, bps: number): number {
  return Math.floor((amount * bps + 5000) / 10000);
}

function wholeNumber(value: number): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function invoiceTotal(
  lines: { qty: number; unit: number; discount: number }[],
  rate: number,
): { subtotal: number; tax: number; total: number } {
  if (!Array.isArray(lines) || lines.length === 0) {
    throw new Error("an invoice needs at least one line");
  }
  if (!wholeNumber(rate) || rate < 0 || rate > 10000) {
    throw new Error("tax rate must be an integer in 0..10000 basis points");
  }
  let subtotal = 0;
  for (const line of lines) {
    if (line === null || typeof line !== "object") {
      throw new Error("line must be a record");
    }
    const { qty, unit, discount } = line;
    if (!wholeNumber(qty) || qty <= 0) {
      throw new Error("qty must be a positive integer");
    }
    if (!wholeNumber(unit) || unit < 0) {
      throw new Error("unit must be a non-negative integer of cents");
    }
    if (!wholeNumber(discount) || discount < 0 || discount > 10000) {
      throw new Error("discount must be an integer in 0..10000 basis points");
    }
    const gross = qty * unit;
    subtotal += gross - halfUp(gross, discount);
  }
  const tax = halfUp(subtotal, rate);
  return { subtotal, tax, total: subtotal + tax };
}
