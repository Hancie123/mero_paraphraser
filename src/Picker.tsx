import { useEffect, useRef } from "react";
import type { Segment } from "./api";

export type PickerPos = { index: number; x: number; y: number };

/** Popup listing the alternatives for one changed segment. Closes on an outside click. */
export default function Picker({
  pos,
  segment,
  onChoose,
  onClose,
}: {
  pos: PickerPos;
  segment: Segment;
  onChoose: (text: string) => void;
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
    </div>
  );
}
