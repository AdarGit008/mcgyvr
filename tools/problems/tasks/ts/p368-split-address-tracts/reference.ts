const LETTERS = "abcd";

function readTract(text: unknown): { start: number; span: number } {
  if (typeof text !== "string") {
    throw new Error("a tract must be a string");
  }
  const slash = text.indexOf("/");
  if (slash === -1) {
    throw new Error("a tract needs a slash");
  }
  const address = text.slice(0, slash);
  const tail = text.slice(slash + 1);
  if (!/^[0-5]$/.test(tail)) {
    throw new Error("the pinned count must be a single digit from 0 to 5");
  }
  const pinned = Number(tail);
  if (address.length !== 5) {
    throw new Error("an address is exactly five letters");
  }
  let start = 0;
  for (let at = 0; at < 5; at += 1) {
    const digit = LETTERS.indexOf(address[at]);
    if (digit === -1) {
      throw new Error("an address is five letters from a to d");
    }
    if (at >= pinned && digit !== 0) {
      throw new Error("a letter past the pinned ones must be a");
    }
    start = start * 4 + digit;
  }
  return { start, span: 4 ** (5 - pinned) };
}

function writeTract(start: number, span: number): string {
  let pinned = 5;
  let width = span;
  while (width > 1) {
    width /= 4;
    pinned -= 1;
  }
  let rest = start;
  let address = "";
  for (let at = 4; at >= 0; at -= 1) {
    const weight = 4 ** at;
    address += LETTERS[Math.floor(rest / weight)];
    rest %= weight;
  }
  return `${address}/${pinned}`;
}

export function splitAddressTracts(
  root: string,
  wants: number[],
): Record<string, unknown> {
  const estate = readTract(root);
  if (!Array.isArray(wants) || wants.length === 0) {
    throw new Error("there must be at least one want");
  }
  for (const want of wants) {
    if (typeof want !== "number" || !Number.isInteger(want) || want < 1) {
      throw new Error("a want must be a whole number above zero");
    }
  }

  const order = wants.map((want, at) => {
    let span = 1;
    while (span < want) {
      span *= 4;
    }
    return { at, span };
  });
  order.sort((a, b) => (b.span === a.span ? a.at - b.at : b.span - a.span));

  const taken: Array<[number, number]> = [];
  const granted: string[] = new Array(wants.length).fill("");
  const end = estate.start + estate.span;
  for (const item of order) {
    let placed = -1;
    if (item.span <= estate.span) {
      for (let start = estate.start; start + item.span <= end; start += item.span) {
        const clash = taken.some(
          ([from, to]) => start < to && from < start + item.span,
        );
        if (!clash) {
          placed = start;
          break;
        }
      }
    }
    if (placed === -1) {
      return { refused: true, tracts: [], spare: estate.span };
    }
    taken.push([placed, placed + item.span]);
    granted[item.at] = writeTract(placed, item.span);
  }

  const used = taken.reduce((sum, [from, to]) => sum + (to - from), 0);
  return { refused: false, tracts: granted, spare: estate.span - used };
}
