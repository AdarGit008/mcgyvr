function checkPolynomial(poly: number[]): void {
  if (!Array.isArray(poly)) {
    throw new Error("a polynomial must be a list");
  }
  for (const coefficient of poly) {
    if (typeof coefficient !== "number" || !Number.isInteger(coefficient)) {
      throw new Error("every coefficient must be a whole number");
    }
  }
  if (poly.length > 0 && poly[poly.length - 1] === 0) {
    throw new Error("a canonical polynomial never ends in a zero coefficient");
  }
}

export function truncatedProduct(
  left: number[],
  right: number[],
  cap: number,
): number[] {
  checkPolynomial(left);
  checkPolynomial(right);
  if (typeof cap !== "number" || !Number.isInteger(cap) || cap < 0) {
    throw new Error("cap must be a whole number of at least zero");
  }
  if (left.length === 0 || right.length === 0) {
    return [];
  }
  const width = Math.min(left.length + right.length - 1, cap + 1);
  const product: number[] = new Array(width).fill(0);
  for (let i = 0; i < left.length; i++) {
    for (let j = 0; j < right.length; j++) {
      if (i + j < width) {
        product[i + j] += left[i] * right[j];
      }
    }
  }
  while (product.length > 0 && product[product.length - 1] === 0) {
    product.pop();
  }
  return product;
}
