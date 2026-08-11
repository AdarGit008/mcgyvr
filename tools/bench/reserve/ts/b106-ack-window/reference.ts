type LinkState = {
  size: number;
  next: number;
  pending: [number, string][];
  delivered: number;
};

export function newLink(size: number): LinkState {
  if (!Number.isInteger(size) || size < 1) {
    throw new Error("size must be a positive integer");
  }
  return { size, next: 0, pending: [], delivered: 0 };
}

export function linkSend(link: LinkState, payload: string): number {
  if (typeof payload !== "string" || payload.length === 0) {
    throw new Error("payload must be a non-empty string");
  }
  if (link.pending.length === link.size) {
    throw new Error("the window is full");
  }
  const seq = link.next;
  link.next += 1;
  link.pending.push([seq, payload]);
  return seq;
}

export function linkAck(link: LinkState, ack: number): string[] {
  if (!Number.isInteger(ack)) {
    throw new Error("ack must be an integer");
  }
  if (ack < -1) {
    throw new Error("an ack below -1 names no frame");
  }
  if (ack >= link.next) {
    throw new Error("cannot acknowledge an unsent frame");
  }
  const freed: string[] = [];
  const kept: [number, string][] = [];
  for (const [seq, payload] of link.pending) {
    if (seq <= ack) {
      freed.push(payload);
    } else {
      kept.push([seq, payload]);
    }
  }
  link.pending = kept;
  link.delivered += freed.length;
  return freed;
}
