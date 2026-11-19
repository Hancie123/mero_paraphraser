import articles from "../python-engine/app/data/articles.json";
import type { Segment } from "./api";

// Prefixes that override the vowel rule; shared with the engine (python-engine/app/utils/text_utils.py).
const AN_EXCEPTIONS: string[] = articles.an;
const A_EXCEPTIONS: string[] = articles.a;

export function wantsAn(word: string): boolean {
  const w = word.toLowerCase();
  if (!w) return false;
  if (AN_EXCEPTIONS.some((p) => w.startsWith(p))) return true;
  if (A_EXCEPTIONS.some((p) => w.startsWith(p))) return false;
  return "aeiou".includes(w[0]);
}

function withArticle(article: string, word: string): string {
  const want = wantsAn(word) ? "an" : "a";
  if (article.toLowerCase() === want) return article;
  return article[0] === article[0].toUpperCase() ? want[0].toUpperCase() + want.slice(1) : want;
}

/** Replace segment `index` with `text`, fixing a preceding "a"/"an". */
export function replaceSegment(segments: Segment[], index: number, text: string): Segment[] {
  const next = segments.map((s) => ({ ...s }));
  next[index].text = text;

  const prev = next[index - 1];
  // No word to agree with (e.g. the span was deleted): leave the article as written.
  if (!prev || !text.trim()) return next;
  // Article at the end of the preceding unchanged chunk: "... a "
  const tail = prev.text.match(/(^|[^\p{L}])(a|an)([ \t]+)$/iu);
  if (tail) {
    const fixed = withArticle(tail[2], text);
    prev.text = prev.text.slice(0, prev.text.length - tail[2].length - tail[3].length) + fixed + tail[3];
    return next;
  }
  // Article as its own (changed) segment followed by a whitespace segment.
  const article = next[index - 2];
  if (article && /^[ \t]+$/.test(prev.text) && /^(a|an)$/i.test(article.text)) {
    article.text = withArticle(article.text, text);
  }
  return next;
}

/**
 * Replace characters `start`..`end` of the joined segments with `text`, as one changed segment.
 *
 * A changed segment the range touches is replaced whole, so the new segment's `original`
 * is always the source wording (and choosing it restores the source). Returns the new
 * segments and the index of the inserted one; a preceding "a"/"an" is fixed as in
 * `replaceSegment`.
 */
export function replaceRange(
  segments: Segment[],
  start: number,
  end: number,
  text: string,
  extra: Pick<Segment, "kind" | "level" | "alternatives">,
): { segments: Segment[]; index: number } {
  // Widen the range to whole changed segments.
  let pos = 0;
  for (const s of segments) {
    const a = pos;
    const b = (pos += s.text.length);
    if (s.original !== undefined && a < end && b > start) {
      start = Math.min(start, a);
      end = Math.max(end, b);
    }
  }
  const out: Segment[] = [];
  let original = "";
  let index = -1;
  pos = 0;
  for (const s of segments) {
    const a = pos;
    const b = (pos += s.text.length);
    if (b <= start || a >= end) {
      if (a >= end && index < 0) index = out.push({ text, original, ...extra }) - 1;
      out.push({ ...s });
      continue;
    }
    if (s.original !== undefined) {
      original += s.original; // fully inside the range (widened above)
      continue;
    }
    if (a < start) out.push({ text: s.text.slice(0, start - a) });
    original += s.text.slice(Math.max(0, start - a), Math.min(s.text.length, end - a));
    if (b > end) {
      index = out.push({ text, original, ...extra }) - 1;
      out.push({ text: s.text.slice(end - a) });
    }
  }
  if (index < 0) index = out.push({ text, original, ...extra }) - 1;
  return { segments: replaceSegment(out, index, text), index };
}

// \p{M} keeps combining marks (Devanagari vowel signs, virama) inside the word.
export const countWords = (text: string) =>
  (text.match(/[\p{L}\p{N}][\p{L}\p{M}\p{N}]*(?:['’][\p{L}\p{M}\p{N}]+)*/gu) ?? []).length;
