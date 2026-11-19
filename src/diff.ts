/** Word-by-word diff between the original text and the paraphrase (Myers' O(ND) algorithm). */

export interface DiffOp {
  type: "equal" | "delete" | "insert";
  text: string;
}

const TOKEN_RE = /\s+|[\p{L}\p{M}\p{N}]+(?:['’][\p{L}\p{M}\p{N}]+)*|[^\s\p{L}\p{M}\p{N}]/gu;

/** Words, runs of whitespace and single punctuation marks; joined they give back `text`. */
export const tokenize = (text: string): string[] => text.match(TOKEN_RE) ?? [];

/** Shortest edit script between token lists, or null when it needs more than `maxEdits` edits. */
function myers(a: string[], b: string[], maxEdits: number): DiffOp[] | null {
  const n = a.length;
  const m = b.length;
  const max = n + m;
  const off = max + 1;
  const v = new Int32Array(2 * max + 3);
  // trace[d] holds v (for k in -(d+1)..d+1) as it was before step d; memory grows with d², not d·(n+m).
  const trace: Int32Array[] = [];
  for (let d = 0; d <= Math.min(max, maxEdits); d++) {
    trace.push(v.slice(off - d - 1, off + d + 2));
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && v[off + k - 1] < v[off + k + 1]) ? v[off + k + 1] : v[off + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) {
        x++;
        y++;
      }
      v[off + k] = x;
      if (x >= n && y >= m) return backtrack(trace, a, b);
    }
  }
  return null;
}

function backtrack(trace: Int32Array[], a: string[], b: string[]): DiffOp[] {
  const ops: DiffOp[] = [];
  let x = a.length;
  let y = b.length;
  for (let d = trace.length - 1; d > 0; d--) {
    const t = trace[d];
    const at = (k: number) => t[k + d + 1];
    const k = x - y;
    const prevK = k === -d || (k !== d && at(k - 1) < at(k + 1)) ? k + 1 : k - 1;
    const prevX = at(prevK);
    const prevY = prevX - prevK;
    while (x > prevX && y > prevY) {
      ops.push({ type: "equal", text: a[--x] });
      y--;
    }
    if (x === prevX) ops.push({ type: "insert", text: b[prevY] });
    else ops.push({ type: "delete", text: a[prevX] });
    x = prevX;
    y = prevY;
  }
  while (x > 0 && y > 0) {
    ops.push({ type: "equal", text: a[--x] });
    y--;
  }
  return ops.reverse();
}

/**
 * Group the token edits into readable change regions: deletions first, then
 * insertions, so "the big red dog" -> "the large brown dog" shows one
 * "big red" -> "large brown" change rather than two interleaved ones.
 */
function regions(ops: DiffOp[]): DiffOp[] {
  const out: DiffOp[] = [];
  let del = "";
  let ins = "";
  const push = (type: DiffOp["type"], text: string) => {
    if (!text) return;
    const last = out[out.length - 1];
    if (last && last.type === type) last.text += text;
    else out.push({ type, text });
  };
  const flush = () => {
    push("delete", del);
    push("insert", ins);
    del = ins = "";
  };
  ops.forEach((op, i) => {
    if (op.type === "delete") del += op.text;
    else if (op.type === "insert") ins += op.text;
    else if ((del || ins) && /^\s+$/.test(op.text) && ops[i + 1] && ops[i + 1].type !== "equal") {
      del += op.text; // a space between two changes belongs to the change
      ins += op.text;
    } else {
      flush();
      push("equal", op.text);
    }
  });
  flush();
  return out;
}

export function diffWords(before: string, after: string, maxEdits = 6000): DiffOp[] {
  const a = tokenize(before);
  const b = tokenize(after);
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let end = 0;
  while (end < a.length - start && end < b.length - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end++;
  const head: DiffOp[] = start ? [{ type: "equal", text: a.slice(0, start).join("") }] : [];
  const tail: DiffOp[] = end ? [{ type: "equal", text: a.slice(a.length - end).join("") }] : [];
  const midA = a.slice(start, a.length - end);
  const midB = b.slice(start, b.length - end);
  const middle = myers(midA, midB, maxEdits) ?? [
    { type: "delete" as const, text: midA.join("") },
    { type: "insert" as const, text: midB.join("") },
  ];
  return regions([...head, ...middle, ...tail]);
}

/** Words removed and added, for the result footer. */
export function diffCounts(ops: DiffOp[]): { removed: number; added: number } {
  const words = (s: string) => tokenize(s).filter((t) => /[\p{L}\p{N}]/u.test(t)).length;
  return {
    removed: ops.filter((o) => o.type === "delete").reduce((n, o) => n + words(o.text), 0),
    added: ops.filter((o) => o.type === "insert").reduce((n, o) => n + words(o.text), 0),
  };
}
