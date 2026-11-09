import { useEffect, useRef, useState } from "react";

export type MenuItem =
  | { separator: true }
  | {
      separator?: false;
      label: string;
      shortcut?: string;
      action: () => void;
      disabled?: boolean;
      /** Shows a checkmark (true) or reserves space for one (false). */
      checked?: boolean;
      /** Radio items show a dot instead of a checkmark. */
      radio?: boolean;
    };

export interface Menu {
  label: string;
  /** Access key letter (shown underlined while Alt is held). */
  key: string;
  items: MenuItem[];
}

type Actionable = Exclude<MenuItem, { separator: true }>;
const isActionable = (i: MenuItem): i is Actionable => !i.separator && !i.disabled;

export default function MenuBar({ menus }: { menus: Menu[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const [hot, setHot] = useState(-1);
  const [altHeld, setAltHeld] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);

  const openMenu = (index: number, firstItem = false) => {
    setOpen(index);
    setHot(firstItem ? menus[index].items.findIndex(isActionable) : -1);
  };
  const close = () => {
    setOpen(null);
    setHot(-1);
  };
  const activate = (item: MenuItem) => {
    if (!isActionable(item)) return;
    close();
    item.action();
  };

  // Alt shows access keys; Alt+letter opens a menu; arrows/Enter/Esc navigate.
  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      if (e.key === "Alt") {
        setAltHeld(true);
        return;
      }
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        const i = menus.findIndex((m) => m.key.toLowerCase() === e.key.toLowerCase());
        if (i >= 0) {
          e.preventDefault();
          openMenu(i, true);
        }
        return;
      }
      if (open === null) return;
      const items = menus[open].items;
      const step = (dir: number) => {
        const len = items.length;
        const start = hot < 0 ? (dir > 0 ? -1 : len) : hot;
        for (let n = 1; n <= len; n++) {
          const j = (((start + dir * n) % len) + len) % len;
          if (isActionable(items[j])) return j;
        }
        return hot;
      };
      switch (e.key) {
        case "Escape":
          e.preventDefault();
          e.stopPropagation();
          close();
          break;
        case "ArrowDown":
          e.preventDefault();
          setHot(step(1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setHot(step(-1));
          break;
        case "ArrowRight":
          e.preventDefault();
          openMenu((open + 1) % menus.length, true);
          break;
        case "ArrowLeft":
          e.preventDefault();
          openMenu((open - 1 + menus.length) % menus.length, true);
          break;
        case "Enter":
        case " ":
          if (hot >= 0) {
            e.preventDefault();
            e.stopPropagation();
            activate(items[hot]);
          }
          break;
        default:
          if (e.key.length === 1) e.preventDefault(); // don't type into the editor while a menu is open
      }
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.key === "Alt") setAltHeld(false);
    };
    const onBlur = () => {
      setAltHeld(false);
      close();
    };
    window.addEventListener("keydown", onDown, true);
    window.addEventListener("keyup", onUp, true);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onDown, true);
      window.removeEventListener("keyup", onUp, true);
      window.removeEventListener("blur", onBlur);
    };
  });

  useEffect(() => {
    if (open === null) return;
    const onDown = (e: MouseEvent) => {
      if (!barRef.current?.contains(e.target as Node)) close();
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div ref={barRef} className="menubar" role="menubar">
      {menus.map((m, i) => (
        <div key={m.label} className="menubar-entry">
          <button
            role="menuitem"
            aria-haspopup="menu"
            aria-expanded={open === i}
            className={open === i ? "menubar-item open" : "menubar-item"}
            // Keep focus (and the caret) in the editor so Edit commands act on it.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => (open === i ? close() : openMenu(i))}
            onMouseEnter={() => open !== null && open !== i && openMenu(i)}
          >
            <AccessLabel label={m.label} accessKey={m.key} show={altHeld || open !== null} />
          </button>
          {open === i && (
            <div className="menu-flyout" role="menu" aria-label={m.label}>
              {m.items.map((item, j) =>
                item.separator ? (
                  <div key={`sep-${j}`} className="menu-sep" role="separator" />
                ) : (
                  <button
                    key={item.label}
                    role={item.checked !== undefined ? (item.radio ? "menuitemradio" : "menuitemcheckbox") : "menuitem"}
                    aria-checked={item.checked}
                    disabled={item.disabled}
                    className={hot === j ? "menu-item hot" : "menu-item"}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setHot(j)}
                    onMouseLeave={() => setHot(-1)}
                    onClick={() => activate(item)}
                  >
                    <span className="menu-check" aria-hidden>
                      {item.checked && (item.radio ? <RadioGlyph /> : <CheckGlyph />)}
                    </span>
                    <span className="menu-label">{item.label}</span>
                    {item.shortcut && <span className="menu-shortcut">{item.shortcut}</span>}
                  </button>
                ),
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function AccessLabel({ label, accessKey, show }: { label: string; accessKey: string; show: boolean }) {
  const i = label.toLowerCase().indexOf(accessKey.toLowerCase());
  if (!show || i < 0) return <>{label}</>;
  return (
    <>
      {label.slice(0, i)}
      <u>{label[i]}</u>
      {label.slice(i + 1)}
    </>
  );
}

const CheckGlyph = () => (
  <svg viewBox="0 0 16 16" width="12" height="12">
    <path d="M3 8.5l3 3 7-7.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const RadioGlyph = () => (
  <svg viewBox="0 0 16 16" width="12" height="12">
    <circle cx="8" cy="8" r="3.5" fill="currentColor" />
  </svg>
);
