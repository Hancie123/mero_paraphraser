import { useCallback, useState } from "react";

/**
 * Undo/redo for the Original text box.
 *
 * Replaces `document.execCommand("undo" | "insertText")`, which is deprecated
 * and doesn't see changes React makes to a controlled textarea anyway. Typing
 * within `COALESCE_MS` is one undo step; paste, cut, drop, open and clear are
 * each a step of their own.
 */
export interface History {
  past: string[];
  present: string;
  future: string[];
  /** When the last coalescing edit happened (0: the next edit starts a new step). */
  lastEdit: number;
}

export const MAX_HISTORY = 200;
export const COALESCE_MS = 800;

export const initHistory = (text = ""): History => ({ past: [], present: text, future: [], lastEdit: 0 });

export function record(h: History, next: string, now: number, coalesce: boolean): History {
  if (next === h.present) return h;
  if (coalesce && h.lastEdit && now - h.lastEdit < COALESCE_MS) {
    return { ...h, present: next, future: [], lastEdit: now };
  }
  return {
    past: [...h.past, h.present].slice(-MAX_HISTORY),
    present: next,
    future: [],
    lastEdit: coalesce ? now : 0,
  };
}

export function undo(h: History): History {
  if (!h.past.length) return h;
  return {
    past: h.past.slice(0, -1),
    present: h.past[h.past.length - 1],
    future: [h.present, ...h.future],
    lastEdit: 0,
  };
}

export function redo(h: History): History {
  if (!h.future.length) return h;
  return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1), lastEdit: 0 };
}

/** Where to put the caret after `before` became `after`: the end of the changed region. */
export function caretAfterChange(before: string, after: string): number {
  let start = 0;
  const max = Math.min(before.length, after.length);
  while (start < max && before[start] === after[start]) start++;
  let end = 0;
  while (end < max - start && before[before.length - 1 - end] === after[after.length - 1 - end]) end++;
  return after.length - end;
}

export function useHistory(initial = "") {
  const [h, setH] = useState(() => initHistory(initial));
  const set = useCallback(
    (next: string, coalesce = false) => setH((cur) => record(cur, next, Date.now(), coalesce)),
    [],
  );
  return {
    text: h.present,
    set,
    undo: useCallback(() => setH(undo), []),
    redo: useCallback(() => setH(redo), []),
    canUndo: h.past.length > 0,
    canRedo: h.future.length > 0,
    /** The text an undo/redo would show, to place the caret. */
    peek: { undo: h.past[h.past.length - 1], redo: h.future[0] },
  };
}
