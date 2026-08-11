/** Read a grouped decimal amount as a whole number of cents. */

export function centsOf(amount: string): number {
  if (typeof amount !== "string") {
    throw new Error("centsOf expects a string");
  }
  const shape = /^(-?)(\d+|\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?$/;
  const found = shape.exec(amount);
  if (found === null) {
    throw new Error("amount does not read as an amount: " + amount);
  }
  const sign = found[1];
  const whole = found[2];
  const decimals = found[3];
  const units = Number(whole.split(",").join(""));
  let cents = 0;
  if (decimals !== undefined) {
    cents = Number(decimals.length === 1 ? decimals + "0" : decimals);
  }
  const total = units * 100 + cents;
  return sign === "-" ? -total : total;
}
