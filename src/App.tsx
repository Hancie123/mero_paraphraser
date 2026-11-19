import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  cleanDocx,
  engineStatus,
  exportDocx,
  fromBase64,
  MAX_CHARS,
  readDocx,
  toBase64,
  MODES,
  paraphrase,
  type Mode,
  type Segment,
  type Stats,
} from "./api";
import MenuBar, { type Menu } from "./MenuBar";
import { countWords, replaceSegment } from "./text";

type EngineState = { state: "starting" } | { state: "ready"; version: string } | { state: "error"; message: string };
type Picker = { index: number; x: number; y: number };
type DialogKind = "about" | "shortcuts" | null;

const LEVELS = ["word", "phrase", "sentence", "added"] as const;
const LEVEL_LABELS: Record<string, string> = {
  word: "Word",
  phrase: "Phrase",
  sentence: "Sentence",
  added: "Added",
};

const STRENGTH_LABELS = ["Light", "Moderate", "Strong"];
const ZOOM_STEPS = [0.8, 0.9, 1, 1.1, 1.25, 1.5];
const APP_VERSION = "0.1.0";

const SHORTCUTS: [string, string][] = [
  ["Paraphrase", "Ctrl+Enter"],
  ["New", "Ctrl+N"],
  ["Open text or Word file", "Ctrl+O"],
  ["Save result", "Ctrl+S"],
  ["Copy result", "Ctrl+Shift+C"],
  ["Zoom in / out", "Ctrl+= / Ctrl+-"],
  ["Reset zoom", "Ctrl+0"],
  ["Open a menu", "Alt+F, Alt+E, Alt+V, Alt+H"],
  ["Close menu or popup", "Esc"],
];

export default function App() {
  const [input, setInput] = useState("");
  const mode: Mode = "humanize";
  const [strength, setStrength] = useState(50);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [engine, setEngine] = useState<EngineState>({ state: "starting" });
  const [highlight, setHighlight] = useState(true);
  const [picker, setPicker] = useState<Picker | null>(null);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const cleanRef = useRef<HTMLInputElement>(null);

  const output = segments.map((s) => s.text).join("");

  useEffect(() => {
    engineStatus()
      .then((r) => {
        setEngine({ state: "ready", version: r.version });
      })
      .catch((e) => setEngine({ state: "error", message: String(e) }));
  }, []);

  const run = useCallback(async () => {
    if (!input.trim() || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setPicker(null);
    try {
      const seed = Math.floor(Math.random() * 2 ** 31);
      const result = await paraphrase(input, mode, strength, seed);
      setSegments(result.segments);
      setStats(result.stats);
      setEngine((e) => (e.state === "ready" ? e : { state: "ready", version: "" }));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [input, strength, busy]);

  /* ---------- commands ---------- */

  const newDoc = () => {
    setInput("");
    setSegments([]);
    setStats(null);
    setError(null);
    editorRef.current?.focus();
  };

  const openFile = () => fileRef.current?.click();

  const onFileChosen = async (file: File | undefined) => {
    if (!file) return;
    try {
      const text = file.name.toLowerCase().endsWith(".docx")
        ? (await readDocx(toBase64(await file.arrayBuffer()))).text
        : await file.text();
      setNotice(null);
      setInput(text.slice(0, MAX_CHARS));
      setSegments([]);
      setStats(null);
      if (text.length > MAX_CHARS) setError(`The file was cut to ${MAX_CHARS.toLocaleString()} characters.`);
    } catch (e) {
      setError(typeof e === "string" ? `That file could not be read: ${e}` : "That file could not be read.");
    }
  };

  /** Saves bytes with the system save dialog (or a download when it isn't available). */
  const saveBytes = async (bytes: Uint8Array, name: string) => {
    const picker = (window as unknown as { showSaveFilePicker?: (o: object) => Promise<FileSystemFileHandle> })
      .showSaveFilePicker;
    const blob = new Blob([bytes as BlobPart], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    if (picker) {
      const handle = await picker({
        suggestedName: name,
        types: [{ description: "Word document", accept: { [blob.type]: [".docx"] } }],
      });
      const w = await handle.createWritable();
      await w.write(blob);
      await w.close();
    } else {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    }
  };

  /** File > Remove personal info from a Word file: cleans a .docx and saves a copy. */
  const onCleanChosen = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      const result = await cleanDocx(toBase64(await file.arrayBuffer()));
      await saveBytes(fromBase64(result.data), file.name.replace(/\.docx$/i, "") + " (clean).docx");
      setNotice(`${file.name}: ${result.removed.join(" ")}`);
    } catch (e) {
      if ((e as DOMException)?.name !== "AbortError") setError(`The document could not be cleaned: ${String(e)}`);
    }
  };

  const saveResult = async () => {
    if (!output) return;
    const picker = (window as unknown as { showSaveFilePicker?: (o: object) => Promise<FileSystemFileHandle> })
      .showSaveFilePicker;
    try {
      if (picker) {
        const handle = await picker({
          suggestedName: "paraphrased.txt",
          types: [
            { description: "Text file", accept: { "text/plain": [".txt"] } },
            {
              description: "Word document (no personal metadata)",
              accept: { "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"] },
            },
          ],
        });
        const w = await handle.createWritable();
        if (handle.name.toLowerCase().endsWith(".docx")) await w.write(fromBase64((await exportDocx(output)).data) as BlobPart);
        else await w.write(output);
        await w.close();
      } else {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([output], { type: "text/plain" }));
        a.download = "paraphrased.txt";
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } catch (e) {
      if ((e as DOMException)?.name !== "AbortError") setError("The file could not be saved.");
    }
  };

  const exit = () => void getCurrentWindow().close();

  /** Runs an editing command on the Original text box. */
  const edit = (command: "undo" | "redo" | "cut" | "copy" | "selectAll") => {
    const el = editorRef.current;
    if (!el) return;
    el.focus();
    if (command === "selectAll") el.select();
    else document.execCommand(command);
  };

  const pasteIntoEditor = async () => {
    const el = editorRef.current;
    try {
      const text = await navigator.clipboard.readText();
      if (!text || !el) return;
      el.focus();
      document.execCommand("insertText", false, text); // keeps Undo working
    } catch {
      setError("Clipboard access was blocked. Paste with Ctrl+V instead.");
    }
  };

  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setInput(text.slice(0, MAX_CHARS));
    } catch {
      setError("Clipboard access was blocked. Paste with Ctrl+V instead.");
    }
  };

  const copy = async () => {
    if (!output) return;
    await navigator.clipboard.writeText(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const useOutput = () => {
    if (!output) return;
    setInput(output);
    setSegments([]);
    setStats(null);
  };

  const applyZoom = (z: number) => {
    setZoom(z);
    getCurrentWebview()
      .setZoom(z)
      .catch(() => {
        document.documentElement.style.setProperty("zoom", String(z));
      });
  };
  const zoomBy = (dir: 1 | -1) => {
    const i = ZOOM_STEPS.indexOf(zoom);
    applyZoom(ZOOM_STEPS[Math.max(0, Math.min(ZOOM_STEPS.length - 1, i + dir))]);
  };

  /* ---------- keyboard ---------- */

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey;
      if (e.key === "Escape") {
        setPicker(null);
        setDialog(null);
        return;
      }
      if (!ctrl || e.altKey) return;
      const k = e.key.toLowerCase();
      const handled = (fn: () => void) => {
        e.preventDefault();
        fn();
      };
      if (k === "enter") handled(() => void run());
      else if (k === "n" && !e.shiftKey) handled(newDoc);
      else if (k === "o" && !e.shiftKey) handled(openFile);
      else if (k === "s" && !e.shiftKey) handled(() => void saveResult());
      else if (k === "c" && e.shiftKey) handled(() => void copy());
      else if (k === "=" || k === "+") handled(() => zoomBy(1));
      else if (k === "-") handled(() => zoomBy(-1));
      else if (k === "0") handled(() => applyZoom(1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    if (!picker) return;
    const onDown = (e: MouseEvent) => {
      if (!pickerRef.current?.contains(e.target as Node)) setPicker(null);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [picker]);

  const openPicker = (index: number, el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const x = Math.min(r.left, window.innerWidth - 240);
    setPicker({ index, x: Math.max(8, x), y: r.bottom + 6 });
  };

  const choose = (text: string) => {
    if (!picker) return;
    const current = segments[picker.index];
    const alternatives = [current.text, ...(current.alternatives ?? [])].filter((a) => a !== text);
    const next = replaceSegment(segments, picker.index, text);
    next[picker.index].alternatives = alternatives;
    setSegments(next);
    setPicker(null);
  };

  const canRun = !busy && !!input.trim() && engine.state !== "error";

  const menus: Menu[] = [
    {
      label: "File",
      key: "F",
      items: [
        { label: "New", shortcut: "Ctrl+N", action: newDoc },
        { label: "Open text or Word file…", shortcut: "Ctrl+O", action: openFile },
        { label: "Save result as…", shortcut: "Ctrl+S", action: () => void saveResult(), disabled: !output },
        { separator: true },
        { label: "Remove personal info from a Word file…", action: () => cleanRef.current?.click() },
        { separator: true },
        { label: "Exit", shortcut: "Alt+F4", action: exit },
      ],
    },
    {
      label: "Edit",
      key: "E",
      items: [
        { label: "Undo", shortcut: "Ctrl+Z", action: () => edit("undo") },
        { label: "Redo", shortcut: "Ctrl+Y", action: () => edit("redo") },
        { separator: true },
        { label: "Cut", shortcut: "Ctrl+X", action: () => edit("cut") },
        { label: "Copy", shortcut: "Ctrl+C", action: () => edit("copy") },
        { label: "Paste", shortcut: "Ctrl+V", action: () => void pasteIntoEditor() },
        { label: "Select all", shortcut: "Ctrl+A", action: () => edit("selectAll") },
        { separator: true },
        { label: "Paraphrase", shortcut: "Ctrl+Enter", action: () => void run(), disabled: !canRun },
        { label: "Copy result", shortcut: "Ctrl+Shift+C", action: () => void copy(), disabled: !output },
        { label: "Use result as input", action: useOutput, disabled: !output },
      ],
    },
    {
      label: "View",
      key: "V",
      items: [
        { label: "Highlight changes", action: () => setHighlight((h) => !h), checked: highlight },
        { separator: true },
        { label: "Zoom in", shortcut: "Ctrl+=", action: () => zoomBy(1), disabled: zoom >= ZOOM_STEPS.at(-1)! },
        { label: "Zoom out", shortcut: "Ctrl+-", action: () => zoomBy(-1), disabled: zoom <= ZOOM_STEPS[0] },
        { label: "Reset zoom", shortcut: "Ctrl+0", action: () => applyZoom(1), disabled: zoom === 1 },
      ],
    },
    {
      label: "Help",
      key: "H",
      items: [
        { label: "Keyboard shortcuts", action: () => setDialog("shortcuts") },
        { separator: true },
        { label: "About Mero Paraphraser", action: () => setDialog("about") },
      ],
    },
  ];

  const inputWords = countWords(input);
  const strengthLabel = STRENGTH_LABELS[Math.min(2, Math.floor(strength / 34))];
  const active = picker ? segments[picker.index] : null;

  return (
    <div className="shell">
      <div className="menubar-row">
        <MenuBar menus={menus} />
        <EngineBadge engine={engine} />
      </div>

      <div className="app">
        <section className="controls">
          <div className="modes" role="tablist" aria-label="Paraphrasing mode">
            {MODES.map((m) => (
              <button
                key={m.id}
                role="tab"
                aria-selected={mode === m.id}
                className={mode === m.id ? "mode active" : "mode"}
                title={m.hint}
              >
                {m.label}
              </button>
            ))}
          </div>
          <label className="strength">
            <span>Changes</span>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={strength}
              style={{ "--pct": `${strength}%` } as CSSProperties}
              onChange={(e) => setStrength(Number(e.target.value))}
            />
            <span className="strength-label">{strengthLabel}</span>
          </label>
        </section>

        <main className="panes">
          <div className="pane">
            <div className="pane-head">
              <span>Original</span>
              <div className="actions">
                <button className="ghost" onClick={paste}>Paste</button>
                <button className="ghost" onClick={() => setInput("")} disabled={!input}>Clear</button>
              </div>
            </div>
            <textarea
              ref={editorRef}
              value={input}
              maxLength={MAX_CHARS}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type or paste the text you want to paraphrase…"
              spellCheck
              autoFocus
            />
            <div className="pane-foot">
              <span>{inputWords} words · {input.length.toLocaleString()}/{MAX_CHARS.toLocaleString()} chars</span>
              <button className="primary" onClick={run} disabled={!canRun}>
                {busy
                  ? "Paraphrasing…"
                  : segments.length
                    ? "Rephrase"
                    : "Paraphrase"}
                <kbd>Ctrl ↵</kbd>
              </button>
            </div>
          </div>

          <div className="pane">
            <div className="pane-head">
              <span>Paraphrased</span>
              <div className="actions">
                <label className="toggle">
                  <input type="checkbox" checked={highlight} onChange={(e) => setHighlight(e.target.checked)} />
                  Highlight changes
                </label>
                <button className="ghost" onClick={useOutput} disabled={!output} title="Use the result as the new input">
                  Use as input
                </button>
                <button className="ghost" onClick={copy} disabled={!output}>{copied ? "Copied" : "Copy"}</button>
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
                      onClick={(e) => openPicker(i, e.currentTarget)}
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
        </main>

        <footer className="footer">Powered by Mero Vision Pvt. Ltd</footer>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept=".txt,.md,.docx,text/plain"
        hidden
        onChange={(e) => {
          void onFileChosen(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <input
        ref={cleanRef}
        type="file"
        accept=".docx"
        hidden
        onChange={(e) => {
          void onCleanChosen(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {picker && active && (
        <div ref={pickerRef} className="picker" style={{ left: picker.x, top: picker.y }} role="menu">
          <div className="picker-head">
            Replace “{active.text.length > 60 ? active.text.slice(0, 57).trimEnd() + "…" : active.text}”
          </div>
          {(active.alternatives ?? []).map((alt) => (
            <button
              key={alt}
              role="menuitem"
              className={active.level === "sentence" ? "picker-sentence" : undefined}
              onClick={() => choose(alt)}
            >
              {alt}
              {alt === active.original && <em>original</em>}
            </button>
          ))}
        </div>
      )}

      {dialog === "about" && (
        <Dialog title="About Mero Paraphraser" onClose={() => setDialog(null)}>
          <p>Rewrite text offline, right on your computer. Nothing you type leaves this device.</p>
          <dl className="about-list">
            <dt>Version</dt>
            <dd>{APP_VERSION}</dd>
            <dt>Engine</dt>
            <dd>
              {engine.state === "ready"
                ? engine.version || "Running"
                : engine.state === "starting"
                  ? "Starting…"
                  : "Unavailable"}
            </dd>
            <dt>Publisher</dt>
            <dd>Mero Vision Pvt. Ltd</dd>
          </dl>
        </Dialog>
      )}

      {dialog === "shortcuts" && (
        <Dialog title="Keyboard shortcuts" onClose={() => setDialog(null)}>
          <table className="shortcut-table">
            <tbody>
              {SHORTCUTS.map(([what, keys]) => (
                <tr key={what}>
                  <td>{what}</td>
                  <td>
                    <kbd>{keys}</kbd>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Dialog>
      )}
    </div>
  );
}

function Dialog({
  title,
  children,
  actions,
  onClose,
}: {
  title: string;
  children: ReactNode;
  /** Extra footer buttons, shown before Close. */
  actions?: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="smoke" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="dialog-body">
          <h2>{title}</h2>
          {children}
        </div>
        <div className="dialog-foot">
          {actions}
          <button className={actions ? "btn" : "primary"} onClick={onClose} autoFocus={!actions}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/** Only shown while the engine is starting or if it failed. */
function EngineBadge({ engine }: { engine: EngineState }) {
  if (engine.state === "ready") return null;
  if (engine.state === "starting") return <span className="badge">Starting engine…</span>;
  return (
    <span className="badge err" title={engine.message}>
      Engine unavailable
    </span>
  );
}
