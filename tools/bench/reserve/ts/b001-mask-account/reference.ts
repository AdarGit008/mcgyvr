/** An account identifier with all but its last digits hidden. */
export function maskAccount(account: string, keep: number): string {
  if (typeof account !== "string") {
    throw new Error("maskAccount expects a string");
  }
  if (!/^[0-9 -]+$/.test(account)) {
    throw new Error("empty account or illegal character");
  }
  if (/^[ -]/.test(account) || /[ -]$/.test(account) || /[ -]{2}/.test(account)) {
    throw new Error("separators must sit between digit groups");
  }
  if (!Number.isInteger(keep) || keep < 1) {
    throw new Error("keep must be a whole number of at least 1");
  }
  const digits = account.replace(/[^0-9]/g, "").length;
  if (digits < keep) {
    throw new Error("fewer digits than keep");
  }
  let hidden = digits - keep;
  let masked = "";
  for (const ch of account) {
    if (ch >= "0" && ch <= "9" && hidden > 0) {
      masked += "*";
      hidden -= 1;
    } else {
      masked += ch;
    }
  }
  return masked;
}
