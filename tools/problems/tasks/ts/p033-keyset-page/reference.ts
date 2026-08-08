export function keysetPage(
  ids: number[],
  cursor: number,
  limit: number,
): { items: number[]; done: boolean } {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("limit must be a positive integer");
  }
  if (!Number.isInteger(cursor)) {
    throw new Error("cursor must be an integer");
  }
  if (!Array.isArray(ids) || ids.some((v) => !Number.isInteger(v))) {
    throw new Error("ids must be a list of integers");
  }
  for (let i = 1; i < ids.length; i++) {
    if (ids[i] <= ids[i - 1]) {
      throw new Error("ids must be strictly increasing");
    }
  }
  const beyond = ids.filter((id) => id > cursor);
  return {
    items: beyond.slice(0, limit),
    done: beyond.length <= limit,
  };
}
