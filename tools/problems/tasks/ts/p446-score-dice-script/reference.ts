const SIZES = new Set([4, 6, 8, 10, 12, 20]);
const GROUP = /^(\d+)d(\d+)(!?)$/;
const WHOLE = /^\d+$/;

export function scoreDiceScript(script: string, rolls: number[]): number {
  if (typeof script !== "string") {
    throw new Error("the script must be a string");
  }
  if (script.length === 0) {
    throw new Error("the script is empty");
  }
  if (!Array.isArray(rolls)) {
    throw new Error("the rolls must be a list");
  }

  let drawn = 0;
  const draw = (size: number): number => {
    if (drawn >= rolls.length) {
      throw new Error("the rolls run out");
    }
    const roll = rolls[drawn];
    drawn += 1;
    if (!Number.isInteger(roll) || roll < 1 || roll > size) {
      throw new Error(`${String(roll)} is not a roll of a ${size}-sided die`);
    }
    return roll;
  };

  const pieces = script.split(/([+-])/);
  let total = 0;
  let sign = 1;
  for (let at = 0; at < pieces.length; at++) {
    if (at % 2 === 1) {
      sign = pieces[at] === "+" ? 1 : -1;
      continue;
    }
    const term = pieces[at];
    if (term.length === 0) {
      throw new Error("the script has an empty term");
    }
    let value = 0;
    if (WHOLE.test(term)) {
      value = Number(term);
    } else {
      const found = GROUP.exec(term);
      if (found === null) {
        throw new Error(`cannot read the term ${term}`);
      }
      const count = Number(found[1]);
      const size = Number(found[2]);
      if (count < 1 || count > 20) {
        throw new Error(`a count of ${count} is outside 1 to 20`);
      }
      if (!SIZES.has(size)) {
        throw new Error(`there is no ${size}-sided die`);
      }
      const open = found[3] === "!";
      for (let die = 0; die < count; die++) {
        let roll = draw(size);
        value += roll;
        while (open && roll === size) {
          roll = draw(size);
          value += roll;
        }
      }
    }
    total += sign * value;
  }

  if (drawn !== rolls.length) {
    throw new Error(`${rolls.length - drawn} rolls were left undrawn`);
  }
  return total;
}
