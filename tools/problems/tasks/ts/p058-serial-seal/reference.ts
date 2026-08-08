export function sealSerial(serial: string): string {
  if (typeof serial !== "string") {
    throw new Error("sealSerial expects a string");
  }
  if (!/^[0-9]{8}$/.test(serial)) {
    throw new Error("serial must be exactly eight digits 0-9");
  }
  const weights = [3, 7, 1, 3, 7, 1, 3, 7];
  let sum = 0;
  for (let i = 0; i < 8; i++) {
    sum += Number(serial[i]) * weights[i];
  }
  const remainder = sum % 11;
  return serial + (remainder === 10 ? "K" : String(remainder));
}
