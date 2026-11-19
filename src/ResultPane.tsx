import { useMemo, useRef, type ReactNode } from "react";
import type { Segment, Stats } from "./api";
import { diffCounts, diffWords } from "./diff";
import { countWords } from "./text";

const LEVELS = ["word", "phrase", "sentence", "added"] as const;
const LEVEL_LABELS: Record<string, string> = {
  word: "Word",
  phrase: "Phrase",
  sentence: "Sentence",
  added: "Added",
};

// A word of the result, as the picker sees it (letters, digits and inner apostrophes).
const WORD_RE = /[\p{L}\p{N}][\p{L}\p{M}\p{N}]*(?:['’][\p{L}\p{M}\p{N}]+)*/gu;
const WORD_CHAR = /[\p{L}\p{M}\p{N}'’]/u;

/** Character offset in the result of a DOM position inside the output (via `data-s` on each piece). */
function offsetOf(node: Node, offset: number): number | null {
  if (node.nodeType === Node.TEXT_NODE) {
    const el = node.parentElement?.closest<HTMLElement>("[data-s]");
    return el ? Number(el.dataset.s) + offset : null;
  }
  const el = node as Element;
  const child = el.childNodes[offset] as Element | undefined;
  const at =
    child?.nodeType === Node.ELEMENT_NODE ? (child.closest?.("[data-s]") ?? child.querySelector("[data-s]")) : null;
  if (at instanceof HTMLElement) return Number(at.dataset.s);
  const last = el.querySelectorAll<HTMLElement>("[data-s]");
  const end = last[last.length - 1];
  return end ? Number(end.dataset.s) + (end.textContent ?? "").length : null;
}

/** "edits": the result with clickable changes. "compare": a word-by-word diff against the original. */
export type ResultView = "edits" | "compare";

/** The "Paraphrased" pane: highlighted result or word diff, change legend and actions. */
export default function ResultPane({
  segments,
  stats,
  output,
  source,
  view,
  onViewChange,
  busy,
  error,
  notice,
  highlight,
  copied,
  onHighlightChange,
  onUseOutput,
  onCopy,
  onOpenPicker,
  onWordClick,
  onSelectRange,
}: {
  segments: Segment[];
  stats: Stats | null;
  /** The result as plain text. */
  output: string;
  /** The text the result was made from. */
  source: string;
  view: ResultView;
  onViewChange: (view: ResultView) => void;
  busy: boolean;
  error: string | null;
  notice: string | null;
  highlight: boolean;
  copied: boolean;
  onHighlightChange: (on: boolean) => void;
  onUseOutput: () => void;
  onCopy: () => void;
  onOpenPicker: (index: number, el: HTMLElement) => void;
  /** Any unchanged word was clicked: characters `start`..`end` of the result. */
  onWordClick: (start: number, end: number, el: HTMLElement) => void;
  /** Two or more words were selected (snapped to whole words). */
  onSelectRange: (start: number, end: number, rect: DOMRect) => void;
}) {
  const outRef = useRef<HTMLDivElement>(null);
  const compare = view === "compare" && segments.length > 0;
  const diff = useMemo(() => (compare ? diffWords(source, output) : []), [compare, source, output]);
  const counts = useMemo(() => diffCounts(diff), [diff]);

  // The result as pieces that each know their character offset (data-s), so clicks and
  // selections map back to the text. Unchanged text is split so every word is clickable.
  const pieces = useMemo(() => {
    const out: ReactNode[] = [];
    let pos = 0;
    segments.forEach((s, i) => {
      const start = pos;
      pos += s.text.length;
      if (s.original !== undefined) {
        const open = (el: HTMLElement) => onOpenPicker(i, el);
        out.push(
          <span
            key={i}
            role="button"
            tabIndex={0}
            data-s={start}
            className={highlight ? `chg on lvl-${s.level ?? "phrase"}` : "chg"}
            title={`${LEVEL_LABELS[s.level ?? "phrase"]} · ${s.kind ?? "Changed"}: “${s.original || "(new)"}” → “${s.text}” · click for alternatives`}
            onClick={(e) => open(e.currentTarget)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                open(e.currentTarget);
              }
            }}
          >
            {s.text}
          </span>,
        );
        return;
      }
      let last = 0;
      for (const m of s.text.matchAll(WORD_RE)) {
        const a = m.index;
        if (a > last)
          out.push(
            <span key={`${i}-${last}`} data-s={start + last}>
              {s.text.slice(last, a)}
            </span>,
          );
        const b = a + m[0].length;
        out.push(
          <span
            key={`${i}-${a}`}
            className="w"
            data-s={start + a}
            onClick={(e) => {
              if (window.getSelection()?.isCollapsed !== false) onWordClick(start + a, start + b, e.currentTarget);
            }}
          >
            {m[0]}
          </span>,
        );
        last = b;
      }
      if (last < s.text.length)
        out.push(
          <span key={`${i}-${last}`} data-s={start + last}>
            {s.text.slice(last)}
          </span>,
        );
    });
    return out;
  }, [segments, highlight, onOpenPicker, onWordClick]);

  // A selection of two or more words opens "Rephrase" for it.
  const onMouseUp = () => {
    window.setTimeout(() => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.rangeCount || compare) return;
      const range = sel.getRangeAt(0);
      if (!outRef.current?.contains(range.commonAncestorContainer)) return;
      const a = offsetOf(range.startContainer, range.startOffset);
      const b = offsetOf(range.endContainer, range.endOffset);
      if (a === null || b === null) return;
      let s = Math.min(a, b);
      let e = Math.max(a, b);
      while (s < e && /\s/.test(output[s])) s++;
      while (e > s && /\s/.test(output[e - 1])) e--;
      while (s > 0 && WORD_CHAR.test(output[s - 1])) s--;
      while (e < output.length && WORD_CHAR.test(output[e])) e++;
      if (countWords(output.slice(s, e)) >= 2) onSelectRange(s, e, range.getBoundingClientRect());
    }, 0);
  };

  return (
    <div className="pane">
      <div className="pane-head">
        <span>Paraphrased</span>
        <div className="actions">
          <div className="seg-toggle" role="group" aria-label="Result view">
            {(["edits", "compare"] as const).map((v) => (
              <button
                key={v}
                aria-pressed={view === v}
                className={view === v ? "on" : ""}
                onClick={() => onViewChange(v)}
                title={
                  v === "edits" ? "The result, with clickable changes" : "Word-by-word comparison with the original"
                }
              >
                {v === "edits" ? "Edits" : "Compare"}
              </button>
            ))}
          </div>
          {view === "edits" && (
            <label className="toggle">
              <input type="checkbox" checked={highlight} onChange={(e) => onHighlightChange(e.target.checked)} />
              Highlight changes
            </label>
          )}
          <button className="ghost" onClick={onUseOutput} disabled={!output} title="Use the result as the new input">
            Use as input
          </button>
          <button className="ghost" onClick={onCopy} disabled={!output}>
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div className={busy ? "progress indeterminate" : "progress"} role="progressbar" aria-hidden={!busy} />
      <div ref={outRef} className={busy ? "output busy" : "output"} aria-live="polite" onMouseUp={onMouseUp}>
        {error ? (
          <p className="error">{error}</p>
        ) : notice && !segments.length ? (
          <p className="notice">{notice}</p>
        ) : compare ? (
          diff.map((op, i) =>
            op.type === "delete" ? (
              <del key={i} className="diff-del">
                {op.text}
              </del>
            ) : op.type === "insert" ? (
              <ins key={i} className="diff-ins">
                {op.text}
              </ins>
            ) : (
              <span key={i}>{op.text}</span>
            ),
          )
        ) : segments.length ? (
          pieces
        ) : (
          <p className="placeholder">
            Your paraphrased text appears here. Click any word for similar words, or select a sentence to rephrase it.
          </p>
        )}
      </div>
      <div className="pane-foot">
        {stats && compare ? (
          <>
            <span>
              {countWords(output)} words · {counts.removed} removed · {counts.added} added
            </span>
            <span className="legend" aria-label="Comparison colours">
              <span className="legend-item diff-key-del">
                <i aria-hidden="true" />
                Removed
              </span>
              <span className="legend-item diff-key-ins">
                <i aria-hidden="true" />
                Added
              </span>
            </span>
          </>
        ) : stats ? (
          <>
            <span>
              {countWords(output)} words · {stats.changes} edits · {stats.change_pct}% of words changed
            </span>
            {highlight && stats.levels && (
              <span className="legend" aria-label="Highlight colours">
                {LEVELS.filter((l) => stats.levels![l]).map((l) => (
                  <span key={l} className={`legend-item lvl-${l}`}>
                    <i aria-hidden="true" />
                    {stats.levels![l]} {LEVEL_LABELS[l].toLowerCase()}
                    {stats.levels![l] === 1 ? "" : l === "added" ? "" : "s"}
                  </span>
                ))}
              </span>
            )}
          </>
        ) : (
          <span>&nbsp;</span>
        )}
      </div>
    </div>
  );
}
