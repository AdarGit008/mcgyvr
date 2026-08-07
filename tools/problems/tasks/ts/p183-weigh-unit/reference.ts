export function weighUnit(
  spec: string,
  masses: Record<string, number>,
): number {
  if (typeof spec !== "string") {
    throw new Error("spec must be a string");
  }
  if (spec.length === 0) {
    throw new Error("spec is empty");
  }
  if (masses === null || typeof masses !== "object") {
    throw new Error("masses must be a table");
  }
  let at = 0;

  const readCount = (): number => {
    if (at >= spec.length || spec[at] < "0" || spec[at] > "9") {
      return 1;
    }
    if (spec[at] === "0") {
      throw new Error("count starts with the digit zero");
    }
    let digits = "";
    while (at < spec.length && spec[at] >= "0" && spec[at] <= "9") {
      digits += spec[at];
      at += 1;
    }
    return Number(digits);
  };

  const readSpec = (): number => {
    let sum = 0;
    let parts = 0;
    while (at < spec.length && spec[at] !== ")" && spec[at] !== "]") {
      const ch = spec[at];
      let weight: number;
      if (ch === "(" || ch === "[") {
        const want = ch === "(" ? ")" : "]";
        at += 1;
        weight = readSpec();
        if (at >= spec.length) {
          throw new Error("opener never answered");
        }
        if (spec[at] !== want) {
          throw new Error("opener answered by the other shape");
        }
        at += 1;
      } else {
        if (ch < "A" || ch > "Z") {
          throw new Error("part does not start with a capital letter");
        }
        at += 1;
        let name = ch;
        while (at < spec.length && spec[at] >= "a" && spec[at] <= "z") {
          if (name.length === 3) {
            throw new Error("name is too long");
          }
          name += spec[at];
          at += 1;
        }
        if (!Object.prototype.hasOwnProperty.call(masses, name)) {
          throw new Error("the table does not hold " + name);
        }
        weight = masses[name];
      }
      sum += weight * readCount();
      parts += 1;
    }
    if (parts === 0) {
      throw new Error("a wrapping with no parts inside it");
    }
    return sum;
  };

  const total = readSpec();
  if (at !== spec.length) {
    throw new Error("closer with nothing open");
  }
  return total;
}
