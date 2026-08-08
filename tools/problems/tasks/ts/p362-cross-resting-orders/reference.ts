type Resting = {
  tag: string;
  side: string;
  price: number;
  size: number;
  at: number;
};

function readOrder(raw: unknown, at: number): Resting {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("an order must be a mapping");
  }
  const row = raw as Record<string, unknown>;
  const tag = row.tag;
  if (typeof tag !== "string" || tag.length === 0) {
    throw new Error("an order needs a non-empty tag");
  }
  const side = row.side;
  if (side !== "bid" && side !== "ask") {
    throw new Error("a side must be bid or ask");
  }
  const price = row.price;
  const size = row.size;
  for (const value of [price, size]) {
    if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
      throw new Error("price and size must be positive whole numbers");
    }
  }
  return {
    tag,
    side,
    price: price as number,
    size: size as number,
    at,
  };
}

export function crossRestingOrders(
  book: Array<Record<string, unknown>>,
  arriving: Record<string, unknown>,
): Record<string, unknown> {
  if (!Array.isArray(book)) {
    throw new Error("the book must be a list");
  }
  const resting = book.map((row, at) => readOrder(row, at));
  const tags = new Set<string>();
  for (const order of resting) {
    if (tags.has(order.tag)) {
      throw new Error("two resting orders share a tag");
    }
    tags.add(order.tag);
  }
  const taker = readOrder(arriving, resting.length);
  if (tags.has(taker.tag)) {
    throw new Error("the arriving tag already rests");
  }
  const bids = resting.filter((order) => order.side === "bid");
  const asks = resting.filter((order) => order.side === "ask");
  if (bids.length > 0 && asks.length > 0) {
    const dearest = Math.max(...bids.map((order) => order.price));
    const cheapest = Math.min(...asks.map((order) => order.price));
    if (dearest >= cheapest) {
      throw new Error("the book already crosses");
    }
  }

  const buying = taker.side === "bid";
  const far = resting.filter(
    (order) =>
      order.side !== taker.side &&
      (buying ? order.price <= taker.price : order.price >= taker.price),
  );
  far.sort((a, b) =>
    a.price === b.price
      ? a.at - b.at
      : buying
        ? a.price - b.price
        : b.price - a.price,
  );

  const trades: Array<Record<string, unknown>> = [];
  let left = taker.size;
  for (const order of far) {
    if (left === 0) {
      break;
    }
    const size = Math.min(left, order.size);
    trades.push({ maker: order.tag, price: order.price, size });
    order.size -= size;
    left -= size;
  }

  const survivors = resting.filter((order) => order.size > 0);
  if (left > 0) {
    survivors.push({ ...taker, size: left });
  }
  const shelf = (side: string, keen: number) =>
    survivors
      .filter((order) => order.side === side)
      .sort((a, b) =>
        a.price === b.price ? a.at - b.at : keen * (a.price - b.price),
      )
      .map((order) => ({
        tag: order.tag,
        side: order.side,
        price: order.price,
        size: order.size,
      }));
  return { trades, book: [...shelf("bid", -1), ...shelf("ask", 1)] };
}
