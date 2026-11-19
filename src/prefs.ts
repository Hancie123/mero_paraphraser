/** The user's word preferences, sent with every paraphrase (see python-engine/app/core/preferences.py). */
export interface WordPrefs {
  /** Terms that never change (product names, technical terms). Matching ignores case. */
  locked: string[];
  /** word or phrase -> the replacement to use whenever the engine swaps it. */
  preferred: Record<string, string>;
  /** Words the engine never puts into the text. */
  banned: string[];
}

export const EMPTY_PREFS: WordPrefs = { locked: [], preferred: {}, banned: [] };

/** Engine limits (MAX_ITEMS, MAX_LEN in preferences.py). */
export const MAX_ITEMS = 500;
export const MAX_LEN = 100;

const KEY = "mero.wordPrefs.v1";

const clean = (s: string) => s.replace(/\s+/g, " ").trim().slice(0, MAX_LEN);

/** One entry per line; blanks and case-insensitive duplicates dropped. */
export function parseList(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of text.split("\n")) {
    const item = clean(line);
    if (item && !seen.has(item.toLowerCase())) {
      seen.add(item.toLowerCase());
      out.push(item);
    }
  }
  return out.slice(0, MAX_ITEMS);
}

/** "word = replacement" (or "->", "→") per line. Lines without a separator are skipped. */
export function parsePreferred(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const m = line.match(/^(.+?)\s*(?:=|->|→)\s*(.+)$/);
    if (!m) continue;
    const word = clean(m[1]).toLowerCase();
    const repl = clean(m[2]);
    if (word && repl && word !== repl.toLowerCase() && Object.keys(out).length < MAX_ITEMS) out[word] = repl;
  }
  return out;
}

export const formatList = (items: string[]) => items.join("\n");
export const formatPreferred = (p: Record<string, string>) =>
  Object.entries(p)
    .map(([w, r]) => `${w} = ${r}`)
    .join("\n");

/** Adds `item` to a list unless it is already there (ignoring case). */
export function addTo(list: string[], item: string): string[] {
  const it = clean(item);
  if (!it || list.some((x) => x.toLowerCase() === it.toLowerCase())) return list;
  return [...list, it].slice(0, MAX_ITEMS);
}

export const hasPrefs = (p: WordPrefs) =>
  p.locked.length > 0 || p.banned.length > 0 || Object.keys(p.preferred).length > 0;

/** The request fields the engine reads. */
export const toRequest = (p: WordPrefs) => ({ locked_terms: p.locked, preferred: p.preferred, banned: p.banned });

const strings = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

export function loadPrefs(): WordPrefs {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (!raw || typeof raw !== "object") return EMPTY_PREFS;
    const preferred: Record<string, string> = {};
    if (raw.preferred && typeof raw.preferred === "object") {
      for (const [k, v] of Object.entries(raw.preferred)) if (typeof v === "string") preferred[k] = v;
    }
    return { locked: strings(raw.locked), preferred, banned: strings(raw.banned) };
  } catch {
    return EMPTY_PREFS; // storage blocked or corrupt: start empty
  }
}

export function savePrefs(p: WordPrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    // storage unavailable: the preferences still apply for this session
  }
}
