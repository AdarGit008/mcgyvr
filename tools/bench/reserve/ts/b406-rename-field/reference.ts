/** Records with one field renamed. */
export function renameField(
  records: Record<string, number>[],
  was: string,
  now: string,
): Record<string, number>[] {
  const out: Record<string, number>[] = [];
  for (const record of records) {
    const copied = { ...record };
    if (was in copied) {
      copied[now] = copied[was];
      delete copied[was];
    }
    out.push(copied);
  }
  return out;
}
