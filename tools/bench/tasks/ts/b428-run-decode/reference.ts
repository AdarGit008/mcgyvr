export function runDecode(coded: string): string {
  let out = "";
  let i = 0;
  while (i < coded.length) {
    const letter = coded[i];
    i += 1;
    let digits = "";
    while (i < coded.length && coded[i] >= "0" && coded[i] <= "9") {
      digits += coded[i];
      i += 1;
    }
    out += letter.repeat(Number(digits));
  }
  return out;
}
