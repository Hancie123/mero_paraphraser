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
