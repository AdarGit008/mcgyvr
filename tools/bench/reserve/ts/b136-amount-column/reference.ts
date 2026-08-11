/** Sum a column of decimal amount strings exactly, by digit arithmetic. */

function addDigits(a: string, b: string): string {
  let carry = 0;
  let out = "";
  const width = Math.max(a.length, b.length);
  for (let i = 0; i < width; i++) {
    const da = i < a.length ? Number(a[a.length - 1 - i]) : 0;
    const db = i < b.length ? Number(b[b.length - 1 - i]) : 0;
    const sum = da + db + carry;
    out = String(sum % 10) + out;
    carry = Math.floor(sum / 10);
  }
  return carry > 0 ? String(carry) + out : out;
}

function groupThousands(digits: string): string {
  let grouped = "";
  for (let i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 === 0) {
      grouped += "_";
    }
    grouped += digits[i];
  }
  return grouped;
}

export function totalAmounts(amounts: string[]): string {
  if (!Array.isArray(amounts) || amounts.length === 0) {
    throw new Error("amounts must be a non-empty list");
  }
  const wholes: string[] = [];
  const fractions: string[] = [];
  for (const amount of amounts) {
    if (typeof amount !== "string") {
      throw new Error("each amount must be a string");
    }
    if (!/^\d(?:_?\d)*(?:\.\d+)?$/.test(amount)) {
      throw new Error(`malformed amount: ${amount}`);
    }
    const bare = amount.replace(/_/g, "");
    const dot = bare.indexOf(".");
    wholes.push(dot === -1 ? bare : bare.slice(0, dot));
    fractions.push(dot === -1 ? "" : bare.slice(dot + 1));
  }
  let scale = 0;
  for (const fraction of fractions) {
    scale = Math.max(scale, fraction.length);
  }
  let total = "0";
  for (let i = 0; i < wholes.length; i++) {
    total = addDigits(total, wholes[i] + fractions[i].padEnd(scale, "0"));
  }
  total = total.replace(/^0+/, "").padStart(scale + 1, "0");
  const whole = groupThousands(total.slice(0, total.length - scale));
  if (scale === 0) {
    return whole;
  }
  return `${whole}.${total.slice(total.length - scale)}`;
}
