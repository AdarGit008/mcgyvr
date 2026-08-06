/** LCS edit script (backward, insertions preferred on ties), zero-context hunks. */
export function diff(a: string[], b: string[]): string[] {
  const n = a.length;
  const m = b.length;
  const dp: number[][] = [];
  for (let i = 0; i <= n; i++) dp.push(new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const ops: { kind: string; line: string }[] = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      ops.push({ kind: "keep", line: a[i - 1] });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] === dp[i][j])) {
      ops.push({ kind: "ins", line: b[j - 1] });
      j -= 1;
    } else {
      ops.push({ kind: "del", line: a[i - 1] });
      i -= 1;
    }
  }
  ops.reverse();
  const out: string[] = [];
  let aLine = 0;
  let bLine = 0;
  let k = 0;
  while (k < ops.length) {
    if (ops[k].kind === "keep") {
      aLine += 1;
      bLine += 1;
      k += 1;
      continue;
    }
    const deletions: string[] = [];
    const insertions: string[] = [];
    const aStart = aLine;
    const bStart = bLine;
    while (k < ops.length && ops[k].kind !== "keep") {
      if (ops[k].kind === "del") {
        deletions.push(ops[k].line);
        aLine += 1;
      } else {
        insertions.push(ops[k].line);
        bLine += 1;
      }
      k += 1;
    }
    const aPart = deletions.length === 0 ? `${aStart},0` : `${aStart + 1},${deletions.length}`;
    const bPart = insertions.length === 0 ? `${bStart},0` : `${bStart + 1},${insertions.length}`;
    out.push(`@@ -${aPart} +${bPart} @@`);
    for (const line of deletions) out.push(`-${line}`);
    for (const line of insertions) out.push(`+${line}`);
  }
  return out;
}
