/** One point-of-sale till session, replayed from its events. */
const OPEN = "open";
const PAYMENT = "payment";
const PAID = "paid";
const CANCELLED = "cancelled";

export function runTillSession(
  events: (string | number)[][],
  prices: Record<string, number>,
): {
  state: string;
  items: [string, number][];
  total: number;
  paid: number;
  change: number;
} {
  for (const name of Object.keys(prices)) {
    if (!Number.isInteger(prices[name]) || prices[name] <= 0) {
      throw new Error("price must be a positive integer: " + name);
    }
  }
  const cart: Record<string, number> = {};
  let state = OPEN;
  let total = 0;
  let paid = 0;
  let change = 0;
  for (const event of events) {
    if (!Array.isArray(event) || event.length === 0) {
      throw new Error("event must be a non-empty list");
    }
    const action = event[0];
    if (state === PAID || state === CANCELLED) {
      throw new Error("no events after " + state);
    }
    if (action === "scan" || action === "void") {
      if (event.length !== 2) {
        throw new Error(String(action) + " takes exactly an item");
      }
      if (state !== OPEN) {
        throw new Error(String(action) + " is lawful only while open");
      }
      const item = event[1];
      if (typeof item !== "string" || !Object.hasOwn(prices, item)) {
        throw new Error("item absent from the price list");
      }
      if (action === "scan") {
        cart[item] = (cart[item] ?? 0) + 1;
      } else {
        if (!Object.hasOwn(cart, item)) {
          throw new Error("void of an item not in the cart");
        }
        cart[item] -= 1;
        if (cart[item] === 0) {
          delete cart[item];
        }
      }
    } else if (action === "close") {
      if (event.length !== 1) {
        throw new Error("close takes no payload");
      }
      if (state !== OPEN) {
        throw new Error("close is lawful only while open");
      }
      const names = Object.keys(cart);
      if (names.length === 0) {
        throw new Error("close with an empty cart");
      }
      total = names.reduce((sum, name) => sum + cart[name] * prices[name], 0);
      state = PAYMENT;
    } else if (action === "pay") {
      if (event.length !== 2) {
        throw new Error("pay takes exactly an amount");
      }
      if (state !== PAYMENT) {
        throw new Error("pay is lawful only during payment");
      }
      const amount = event[1];
      if (typeof amount !== "number" || !Number.isInteger(amount) || amount <= 0) {
        throw new Error("pay amount must be a positive integer");
      }
      paid += amount;
      if (paid >= total) {
        change = paid - total;
        state = PAID;
      }
    } else if (action === "cancel") {
      if (event.length !== 1) {
        throw new Error("cancel takes no payload");
      }
      state = CANCELLED;
    } else {
      throw new Error("unknown action: " + String(action));
    }
  }
  const items: [string, number][] = Object.keys(cart)
    .sort()
    .map((name) => [name, cart[name]]);
  return { state, items, total, paid, change };
}
