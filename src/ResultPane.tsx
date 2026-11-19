import { useMemo } from "react";
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
}) {
  const compare = view === "compare" && segments.length > 0;
  const diff = useMemo(() => (compare ? diffWords(source, output) : []), [compare, source, output]);
  const counts = useMemo(() => diffCounts(diff), [diff]);

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
      <div className={busy ? "output busy" : "output"} aria-live="polite">
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
          segments.map((s, i) =>
            s.original !== undefined ? (
              <button
                key={i}
                className={highlight ? `chg on lvl-${s.level ?? "phrase"}` : "chg"}
                title={`${LEVEL_LABELS[s.level ?? "phrase"]} · ${s.kind ?? "Changed"}: “${s.original || "(new)"}” → “${s.text}” · click for alternatives`}
                onClick={(e) => onOpenPicker(i, e.currentTarget)}
              >
                {s.text}
              </button>
            ) : (
              <span key={i}>{s.text}</span>
            ),
          )
        ) : (
          <p className="placeholder">
            Your paraphrased text appears here. Click a highlighted word to pick a different alternative.
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
