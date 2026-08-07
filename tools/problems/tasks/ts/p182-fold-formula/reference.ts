export function foldFormula(recipe: string): string {
  if (typeof recipe !== "string") {
    throw new Error("recipe must be a string");
  }
  if (recipe.length === 0) {
    throw new Error("empty recipe");
  }
  let at = 0;

  const readRepeat = (): number => {
    if (at >= recipe.length || recipe[at] < "0" || recipe[at] > "9") {
      return 1;
    }
    if (recipe[at] === "0") {
      throw new Error("repeat begins with a zero");
    }
    let digits = "";
    while (at < recipe.length && recipe[at] >= "0" && recipe[at] <= "9") {
      digits += recipe[at];
      at += 1;
    }
    return Number(digits);
  };

  const readRecipe = (): Map<string, number> => {
    const tally = new Map<string, number>();
    let items = 0;
    while (at < recipe.length && recipe[at] !== ")") {
      let body: Map<string, number>;
      if (recipe[at] === "(") {
        at += 1;
        body = readRecipe();
        if (at >= recipe.length || recipe[at] !== ")") {
          throw new Error("parenthesis left open");
        }
        at += 1;
      } else {
        const head = recipe[at];
        if (head < "A" || head > "Z") {
          throw new Error("item does not start with an uppercase letter");
        }
        at += 1;
        let tag = head;
        while (at < recipe.length && recipe[at] >= "a" && recipe[at] <= "z") {
          if (tag.length === 3) {
            throw new Error("tag carries three lowercase letters");
          }
          tag += recipe[at];
          at += 1;
        }
        body = new Map([[tag, 1]]);
      }
      const repeat = readRepeat();
      for (const [tag, count] of body) {
        tally.set(tag, (tally.get(tag) ?? 0) + count * repeat);
      }
      items += 1;
    }
    if (items === 0) {
      throw new Error("parentheses enclose nothing");
    }
    return tally;
  };

  const totals = readRecipe();
  if (at !== recipe.length) {
    throw new Error("closing parenthesis with no opener");
  }
  return [...totals.keys()]
    .sort()
    .map((tag) => (totals.get(tag) === 1 ? tag : tag + String(totals.get(tag))))
    .join("");
}
