/** Recursive-descent evaluator: expr -> term -> factor, with unary minus. */
export function evaluate(expr: string): number {
  let pos = 0;
  const skip = (): void => {
    while (expr[pos] === " ") pos += 1;
  };
  const fail = (message: string): never => {
    throw new Error(`${message} at position ${pos}`);
  };
  const parseFactor = (): number => {
    skip();
    if (expr[pos] === "-") {
      pos += 1;
      return -parseFactor();
    }
    if (expr[pos] === "(") {
      pos += 1;
      const value = parseExpr();
      skip();
      if (expr[pos] !== ")") fail("expected ')'");
      pos += 1;
      return value;
    }
    const start = pos;
    while (pos < expr.length && expr[pos] >= "0" && expr[pos] <= "9") pos += 1;
    if (pos === start) fail("expected a number");
    return Number(expr.slice(start, pos));
  };
  const parseTerm = (): number => {
    let value = parseFactor();
    skip();
    while (expr[pos] === "*" || expr[pos] === "/") {
      const op = expr[pos];
      pos += 1;
      const rhs = parseFactor();
      if (op === "/" && rhs === 0) fail("division by zero");
      value = op === "*" ? value * rhs : value / rhs;
      skip();
    }
    return value;
  };
  const parseExpr = (): number => {
    let value = parseTerm();
    skip();
    while (expr[pos] === "+" || expr[pos] === "-") {
      const op = expr[pos];
      pos += 1;
      const rhs = parseTerm();
      value = op === "+" ? value + rhs : value - rhs;
      skip();
    }
    return value;
  };
  const result = parseExpr();
  skip();
  if (pos !== expr.length) fail("unexpected trailing input");
  return result;
}
