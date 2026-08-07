const KEYS: Record<string, string> = {
  "0": " ",
  "2": "ABC",
  "3": "DEF",
  "4": "GHI",
  "5": "JKL",
  "6": "MNO",
  "7": "PQRS",
  "8": "TUV",
  "9": "WXYZ",
};

export function decodeTapKeys(taps: string): string {
  if (typeof taps !== "string") {
    throw new Error("the tap sequence must be a string");
  }
  if (taps.length === 0) {
    throw new Error("the tap sequence is empty");
  }
  if (taps.startsWith("-") || taps.endsWith("-")) {
    throw new Error("a hyphen may not sit at either end");
  }
  if (taps.includes("--")) {
    throw new Error("two hyphens in a row");
  }

  let text = "";
  let key = "";
  let taken = 0;

  const settle = (): void => {
    if (taken > 0) {
      text += KEYS[key][taken - 1];
    }
    key = "";
    taken = 0;
  };

  for (const mark of taps) {
    if (mark === "-") {
      settle();
      continue;
    }
    if (!Object.hasOwn(KEYS, mark)) {
      throw new Error(`key ${mark} carries no letters`);
    }
    if (mark !== key) {
      settle();
      key = mark;
    }
    taken += 1;
    if (taken > KEYS[key].length) {
      throw new Error(`key ${key} does not carry ${taken} letters`);
    }
  }
  settle();
  return text;
}
