import type { Segment } from "./api";

const AN_EXCEPTIONS = ["hour", "honest", "honor", "honour", "heir"];
const A_EXCEPTIONS = [
  "unique", "unit", "univ", "unif", "union", "unicorn", "usual", "use", "usa",
  "utili", "utop", "euro", "eu", "one", "once", "ufo",
];

export function wantsAn(word: string): boolean {
  const w = word.toLowerCase();
  if (AN_EXCEPTIONS.some((p) => w.startsWith(p))) return true;
  if (A_EXCEPTIONS.some((p) => w.startsWith(p))) return false;
  return "aeiou".includes(w[0] ?? "");
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
  if (!prev) return next;
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

export const countWords = (text: string) => (text.match(/[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)*/gu) ?? []).length;
