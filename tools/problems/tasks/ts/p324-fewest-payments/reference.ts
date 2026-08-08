function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function person(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

export function fewestPayments(dues: any): (string | number)[][] {
  if (!Array.isArray(dues)) {
    throw new Error("the dues must be a list");
  }
  const position = new Map<string, number>();
  for (const due of dues) {
    if (!Array.isArray(due) || due.length !== 3) {
      throw new Error("a due must be a list of exactly three items");
    }
    const [payer, payee, amount] = due;
    if (!person(payer) || !person(payee)) {
      throw new Error("a name must be a non-empty string");
    }
    if (payer === payee) {
      throw new Error("a due must not put one person on both sides");
    }
    if (!whole(amount) || amount < 1) {
      throw new Error("an amount must be a whole number of one or more");
    }
    position.set(payer, (position.get(payer) ?? 0) - amount);
    position.set(payee, (position.get(payee) ?? 0) + amount);
  }

  const red = new Map<string, number>();
  const black = new Map<string, number>();
  for (const [name, net] of position) {
    if (net < 0) red.set(name, -net);
    if (net > 0) black.set(name, net);
  }

  const payments: (string | number)[][] = [];
  while (red.size > 0) {
    const redNames = [...red.keys()].sort();
    const blackNames = [...black.keys()].sort();
    let payer = "";
    let payee = "";
    for (const name of redNames) {
      for (const other of blackNames) {
        if (red.get(name) === black.get(other)) {
          payer = name;
          payee = other;
          break;
        }
      }
      if (payer !== "") break;
    }
    if (payer === "") {
      for (const name of redNames) {
        if (payer === "" || (red.get(name) as number) > (red.get(payer) as number)) {
          payer = name;
        }
      }
      for (const other of blackNames) {
        if (
          payee === "" ||
          (black.get(other) as number) > (black.get(payee) as number)
        ) {
          payee = other;
        }
      }
    }
    const owed = red.get(payer) as number;
    const due = black.get(payee) as number;
    const moved = owed < due ? owed : due;
    payments.push([payer, payee, moved]);
    if (owed === moved) red.delete(payer);
    else red.set(payer, owed - moved);
    if (due === moved) black.delete(payee);
    else black.set(payee, due - moved);
  }
  return payments;
}
