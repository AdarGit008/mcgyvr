type Spot = { key: number; presses: number };

export function planKeyPresses(text: string, layout: string[]): string {
  if (typeof text !== "string") {
    throw new Error("the text must be a string");
  }
  if (text.length === 0) {
    throw new Error("the text is empty");
  }
  if (!Array.isArray(layout) || layout.length !== 10) {
    throw new Error("the layout is exactly ten keys");
  }

  const place = new Map<string, Spot>();
  for (let key = 0; key < layout.length; key++) {
    const carried = layout[key];
    if (typeof carried !== "string") {
      throw new Error(`key ${key} does not carry a string`);
    }
    for (let at = 0; at < carried.length; at++) {
      const mark = carried[at];
      if (place.has(mark)) {
        throw new Error(`the layout lists ${mark} more than once`);
      }
      place.set(mark, { key, presses: at + 1 });
    }
  }

  const parts: string[] = [];
  let previous = -1;
  for (const mark of text) {
    const spot = place.get(mark);
    if (spot === undefined) {
      throw new Error(`${mark} sits on no key`);
    }
    if (spot.key === previous) {
      parts.push(".");
    }
    parts.push(String(spot.key).repeat(spot.presses));
    previous = spot.key;
  }
  return parts.join("");
}
