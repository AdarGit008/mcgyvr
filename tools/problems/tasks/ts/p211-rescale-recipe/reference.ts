const ROW =
  /^(?:([1-9][0-9]*) ([1-9][0-9]*)\/([1-9][0-9]*)|([1-9][0-9]*)\/([1-9][0-9]*)|([1-9][0-9]*)) (tsp|tbsp|cup|egg|g) ([A-Za-z]+(?: [A-Za-z]+)*)$/;

const GRAIN: Record<string, number[]> = {
  tsp: [1, 4],
  tbsp: [1, 2],
  cup: [1, 8],
  egg: [1, 1],
  g: [1, 1],
};

function commonFactor(a: number, b: number): number {
  let big = a;
  let small = b;
  while (small !== 0) {
    const rest = big % small;
    big = small;
    small = rest;
  }
  return big;
}

function checkPart(top: number, bottom: number): void {
  if (top >= bottom) {
    throw new Error("a part must be smaller than one: " + top + "/" + bottom);
  }
  if (commonFactor(top, bottom) !== 1) {
    throw new Error("a part must already be reduced: " + top + "/" + bottom);
  }
}

export function rescaleRecipe(
  lines: string[],
  num: number,
  den: number,
): string[] {
  if (!Array.isArray(lines)) {
    throw new Error("the recipe must be a list of rows");
  }
  for (const side of [num, den]) {
    if (typeof side !== "number" || !Number.isInteger(side) || side < 1) {
      throw new Error("the ratio must be two whole numbers above zero");
    }
  }
  const carried = new Set<string>();
  const out: string[] = [];

  for (const row of lines) {
    if (typeof row !== "string") {
      throw new Error("every row must be a string");
    }
    const hit = ROW.exec(row);
    if (hit === null) {
      throw new Error("the row breaks its shape: " + row);
    }
    let over = 0;
    let under = 1;
    if (hit[1] !== undefined) {
      const whole = Number(hit[1]);
      const top = Number(hit[2]);
      const bottom = Number(hit[3]);
      checkPart(top, bottom);
      over = whole * bottom + top;
      under = bottom;
    } else if (hit[4] !== undefined) {
      const top = Number(hit[4]);
      const bottom = Number(hit[5]);
      checkPart(top, bottom);
      over = top;
      under = bottom;
    } else {
      over = Number(hit[6]);
      under = 1;
    }
    const unit = hit[7];
    const ingredient = hit[8];
    if (carried.has(ingredient)) {
      throw new Error("two rows carry the same ingredient: " + ingredient);
    }
    carried.add(ingredient);

    const grain = GRAIN[unit];
    const top = over * num * grain[1];
    const bottom = under * den * grain[0];
    let grains = Math.floor((2 * top + bottom) / (2 * bottom));
    if (grains === 0) {
      grains = 1;
    }
    let value = grains * grain[0];
    let scale = grain[1];
    const shared = commonFactor(value, scale);
    value = value / shared;
    scale = scale / shared;

    let amount: string;
    if (scale === 1) {
      amount = String(value);
    } else {
      const whole = Math.floor(value / scale);
      const rest = value % scale;
      amount = whole === 0 ? rest + "/" + scale : whole + " " + rest + "/" + scale;
    }
    out.push(amount + " " + unit + " " + ingredient);
  }
  return out;
}
