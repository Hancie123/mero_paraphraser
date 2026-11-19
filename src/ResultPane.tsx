import type { Segment, Stats } from "./api";
import { countWords } from "./text";

const LEVELS = ["word", "phrase", "sentence", "added"] as const;
const LEVEL_LABELS: Record<string, string> = {
  word: "Word",
  phrase: "Phrase",
  sentence: "Sentence",
  added: "Added",
};

/** The "Paraphrased" pane: highlighted result, change legend and actions. */
export default function ResultPane({
  segments,
  stats,
  output,
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
  return (
    <div className="pane">
      <div className="pane-head">
        <span>Paraphrased</span>
        <div className="actions">
          <label className="toggle">
            <input type="checkbox" checked={highlight} onChange={(e) => onHighlightChange(e.target.checked)} />
            Highlight changes
          </label>
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
        {stats ? (
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
