import { useEffect, useRef } from "react";
import type { Segment } from "./api";

export type PickerPos = { index: number; x: number; y: number };

/** Popup listing the alternatives for one changed segment. Closes on an outside click. */
export default function Picker({
  pos,
  segment,
  onChoose,
  onKeep,
  onBan,
  onClose,
}: {
  pos: PickerPos;
  segment: Segment;
  onChoose: (text: string) => void;
  /** Never change the original word again (adds it to the locked terms). */
  onKeep?: (word: string) => void;
  /** Never use the new word again (adds it to the banned words). */
  onBan?: (word: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [onClose]);

  const label = segment.text.length > 60 ? segment.text.slice(0, 57).trimEnd() + "…" : segment.text;
  // Word-level swaps only: a whole rewritten sentence is no "term".
  const word = segment.level === "word" && segment.original && segment.text.trim() ? segment : null;
  return (
    <div ref={ref} className="picker" style={{ left: pos.x, top: pos.y }} role="menu">
      <div className="picker-head">Replace “{label}”</div>
      {(segment.alternatives ?? []).map((alt) => (
        <button
          key={alt}
          role="menuitem"
          className={segment.level === "sentence" ? "picker-sentence" : undefined}
          onClick={() => onChoose(alt)}
        >
          {alt}
          {alt === segment.original && <em>original</em>}
        </button>
      ))}
      {word && (onKeep || onBan) && (
        <div className="picker-actions">
          {onKeep && (
            <button role="menuitem" onClick={() => onKeep(word.original!)}>
              Always keep “{word.original}”
            </button>
          )}
          {onBan && (
            <button role="menuitem" onClick={() => onBan(word.text)}>
              Never use “{word.text}”
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** One group of options in a `SuggestPicker`, e.g. one meaning of a word. */
export interface SuggestGroup {
  /** "verb · establish the validity of something"; empty for an unlabelled group. */
  label: string;
  options: string[];
}

/** What the user clicked or selected in the result: characters `start`..`end` of it. */
export interface SuggestTarget {
  start: number;
  end: number;
  text: string;
  kind: "word" | "sentence";
  x: number;
  y: number;
}

/**
 * Popup for any word (similar words, grouped by meaning) or a selected sentence
 * (a few rephrased versions). Closes on an outside click.
 */
export function SuggestPicker({
  target,
  groups,
  loading,
  note,
  error,
  onChoose,
  onRetry,
  onClose,
}: {
  target: SuggestTarget;
  groups: SuggestGroup[];
  loading: boolean;
  /** A warning shown above the options (e.g. the word sets how certain a claim is). */
  note?: string;
  error?: string;
  onChoose: (text: string) => void;
  /** Sentences only: ask for new versions. */
  onRetry?: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [onClose]);

  const sentence = target.kind === "sentence";
  const label = target.text.length > 60 ? target.text.slice(0, 57).trimEnd() + "…" : target.text;
  const empty = !loading && !error && groups.every((g) => !g.options.length);
  return (
    <div
      ref={ref}
      className={sentence ? "picker picker-wide" : "picker"}
      style={{ left: target.x, top: target.y }}
      role="menu"
      aria-busy={loading}
    >
      <div className="picker-head">{sentence ? `Rephrase “${label}”` : `Similar to “${label}”`}</div>
      {note && <div className="picker-note">{note}</div>}
      {loading && <div className="picker-status">{sentence ? "Writing new versions…" : "Looking up…"}</div>}
      {error && <div className="picker-status">{error}</div>}
      {empty && (
        <div className="picker-status">{sentence ? "No different version found." : "No similar words found."}</div>
      )}
      {groups.map((g, i) =>
        g.options.length ? (
          <div key={i} className="picker-group" role="group" aria-label={g.label || undefined}>
            {g.label && <div className="picker-gloss">{g.label}</div>}
            {g.options.map((opt) => (
              <button
                key={opt}
                role="menuitem"
                className={sentence ? "picker-sentence" : undefined}
                onClick={() => onChoose(opt)}
              >
                {opt}
              </button>
            ))}
          </div>
        ) : null,
      )}
      {sentence && onRetry && !loading && (
        <div className="picker-actions">
          <button role="menuitem" onClick={onRetry}>
            Try other versions
          </button>
        </div>
      )}
    </div>
  );
}
