import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  aiCommand,
  engineStatus,
  MAX_CHARS,
  MODES,
  paraphrase,
  type AiStatus,
  type Mode,
  type Report,
  type Segment,
  type Stats,
} from "./api";
import MenuBar, { type Menu } from "./MenuBar";
import { countWords, replaceSegment } from "./text";

type EngineState = { state: "starting" } | { state: "ready"; version: string } | { state: "error"; message: string };
type Picker = { index: number; x: number; y: number };
type DialogKind = "about" | "shortcuts" | null;

const STRENGTH_LABELS = ["Light", "Moderate", "Strong"];
const ZOOM_STEPS = [0.8, 0.9, 1, 1.1, 1.25, 1.5];
const APP_VERSION = "0.1.0";

const SHORTCUTS: [string, string][] = [
  ["Paraphrase", "Ctrl+Enter"],
  ["New", "Ctrl+N"],
  ["Open text file", "Ctrl+O"],
  ["Save result", "Ctrl+S"],
  ["Copy result", "Ctrl+Shift+C"],
  ["Zoom in / out", "Ctrl+= / Ctrl+-"],
  ["Reset zoom", "Ctrl+0"],
  ["Open a menu", "Alt+F, Alt+E, Alt+V, Alt+H"],
  ["Close menu or popup", "Esc"],
];

export default function App() {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("standard");
  const [strength, setStrength] = useState(50);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [view, setView] = useState<"text" | "review">("text");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [engine, setEngine] = useState<EngineState>({ state: "starting" });
  const [highlight, setHighlight] = useState(true);
  const [picker, setPicker] = useState<Picker | null>(null);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const output = segments.map((s) => s.text).join("");
  const aiReady = ai?.state === "ready";

  useEffect(() => {
    engineStatus()
      .then((r) => {
        setEngine({ state: "ready", version: r.version });
        setAi(r.ai);
        // No model yet (dev, or installed without the "ai" folder): fetch it automatically.
        if (r.ai.state === "missing") aiCommand("download").then(setAi).catch(() => {});
      })
      .catch((e) => setEngine({ state: "error", message: String(e) }));
  }, []);

  // Keep the AI status fresh while downloading or loading the model.
  const aiBusy = ai?.state === "downloading" || ai?.state === "verifying" || ai?.server === "starting";
  useEffect(() => {
    if (!aiBusy) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const s = await aiCommand("status");
        if (alive) setAi(s);
      } catch {
        /* engine busy or restarting; try again */
      }
      if (alive) timer = setTimeout(tick, 700);
    };
    timer = setTimeout(tick, 700);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [aiBusy]);

  // Load the model in the background as soon as it's installed.
  useEffect(() => {
    if (aiReady && ai?.server === "stopped") {
      aiCommand("warm").then(setAi).catch(() => {});
    }
  }, [aiReady, ai?.server]);

  const retryDownload = () => aiCommand("download").then(setAi).catch((e) => setError(String(e)));

  const run = useCallback(async () => {
    if (!input.trim() || busy) return;
    setBusy(true);
    setError(null);
    setPicker(null);
    try {
      const seed = Math.floor(Math.random() * 2 ** 31);
      const result = await paraphrase(input, mode, strength, seed, aiReady ? "ai" : "basic");
      setSegments(result.segments);
      setStats(result.stats);
      setReport(result.report ?? null);
      setEngine((e) => (e.state === "ready" ? e : { state: "ready", version: "" }));
      if (result.engine === "ai") setAi((a) => (a ? { ...a, server: "running" } : a));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [input, mode, strength, busy, aiReady]);

  /* ---------- commands ---------- */

  const newDoc = () => {
    setInput("");
    setSegments([]);
    setStats(null);    setReport(null);    setView("text");
    setError(null);
    editorRef.current?.focus();
  };

  const openFile = () => fileRef.current?.click();

  const onFileChosen = async (file: File | undefined) => {
    if (!file) return;
    try {
      const text = await file.text();
      setInput(text.slice(0, MAX_CHARS));
      setSegments([]);
      setStats(null);      setReport(null);      setView("text");
      if (text.length > MAX_CHARS) setError(`The file was cut to ${MAX_CHARS.toLocaleString()} characters.`);
    } catch {
      setError("That file could not be read.");
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
          types: [{ description: "Text file", accept: { "text/plain": [".txt"] } }],
        });
        const w = await handle.createWritable();
        await w.write(output);
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
    setStats(null);    setReport(null);    setView("text");
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
        { label: "Open text file…", shortcut: "Ctrl+O", action: openFile },
        { label: "Save result as…", shortcut: "Ctrl+S", action: () => void saveResult(), disabled: !output },
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
        ...MODES.map((m) => ({
          label: `${m.label} mode`,
          action: () => setMode(m.id),
          checked: mode === m.id,
          radio: true,
        })),
        { separator: true },
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
        {engine.state !== "ready" ? <EngineBadge engine={engine} /> : <AiBadge ai={ai} />}
      </div>

      {ai?.state === "error" && (
        <InfoBar severity="error" title="The AI model download didn't finish" message={ai.message}>
          <button className="btn" onClick={() => void retryDownload()}>Try again</button>
        </InfoBar>
      )}

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
                onClick={() => setMode(m.id)}
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
                  ? aiReady && ai?.server !== "running"
                    ? "Loading AI model…"
                    : "Paraphrasing…"
                  : segments.length
                    ? "Rephrase"
                    : "Paraphrase"}
                <kbd>Ctrl ↵</kbd>
              </button>
            </div>
          </div>

          <div className="pane">
            <div className="pane-head">
              <div className="pane-tabs" role="tablist" aria-label="Result view">
                <button
                  role="tab"
                  aria-selected={view === "text"}
                  className={view === "text" ? "pane-tab active" : "pane-tab"}
                  onClick={() => setView("text")}
                >
                  Paraphrased
                </button>
                <button
                  role="tab"
                  aria-selected={view === "review"}
                  className={view === "review" ? "pane-tab active" : "pane-tab"}
                  onClick={() => setView("review")}
                  disabled={!report}
                >
                  Review
                  {report && report.warnings.length > 0 && <span className="tab-dot" aria-label="has warnings" />}
                </button>
              </div>
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
            {view === "review" && report ? (
              <ReviewPanel report={report} />
            ) : (
            <div className={busy ? "output busy" : "output"} aria-live="polite">
              {error ? (
                <p className="error">{error}</p>
              ) : segments.length ? (
                segments.map((s, i) =>
                  s.original !== undefined ? (
                    <button
                      key={i}
                      className={highlight ? "chg on" : "chg"}
                      title={`${s.kind ?? "Changed"}: “${s.original || "(new)"}” → “${s.text}” · click for alternatives`}
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
            )}
            <div className="pane-foot">
              {stats ? (
                <span>
                  {countWords(output)} words · {stats.changes} edits · {stats.change_pct}% of words changed
                </span>
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
        accept=".txt,.md,text/plain"
        hidden
        onChange={(e) => {
          void onFileChosen(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {picker && active && (
        <div ref={pickerRef} className="picker" style={{ left: picker.x, top: picker.y }} role="menu">
          <div className="picker-head">Replace “{active.text}”</div>
          {(active.alternatives ?? []).map((alt) => (
            <button key={alt} role="menuitem" onClick={() => choose(alt)}>
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

const LAYER_ICONS: Record<string, string> = { ok: "✓", warning: "!" };

/** Layer 8 view: what each of the eight layers did, plus plain-language explanations. */
function ReviewPanel({ report }: { report: Report }) {
  return (
    <div className="review" aria-live="polite">
      {report.explanations.length > 0 && (
        <section>
          <h3>What changed</h3>
          <ul className="explanations">
            {report.explanations.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h3>Processing layers</h3>
        <ol className="layers">
          {report.layers.map((l, i) => (
            <li key={l.id} className={`layer ${l.status}`}>
              <span className="layer-icon" aria-label={l.status === "ok" ? "Passed" : "Warning"}>
                {LAYER_ICONS[l.status]}
              </span>
              <div>
                <div className="layer-name">
                  <span className="layer-num">Layer {i + 1}</span> {l.name}
                </div>
                <div className="layer-detail">{l.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function InfoBar({
  title,
  message,
  severity = "info",
  onClose,
  children,
}: {
  title: string;
  message: string;
  severity?: "info" | "error";
  onClose?: () => void;
  children?: ReactNode;
}) {
  return (
    <div className={`infobar ${severity}`} role={severity === "error" ? "alert" : "status"}>
      <span className="infobar-icon" aria-hidden>
        {severity === "error" ? "!" : "i"}
      </span>
      <div className="infobar-text">
        <strong>{title}</strong>
        <span>{message}</span>
      </div>
      <div className="infobar-actions">{children}</div>
      {onClose && (
        <button className="infobar-close ghost" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden>
            <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </div>
  );
}

/** Shows AI download or loading progress; nothing when idle. */
function AiBadge({ ai }: { ai: AiStatus | null }) {
  if (!ai) return null;
  let text: string | null = null;
  if (ai.state === "downloading") {
    text = `Downloading AI model · ${Math.floor((100 * ai.done_bytes) / (ai.size_bytes || 1))}%`;
  } else if (ai.state === "verifying") {
    text = "Checking AI model…";
  } else if (ai.state === "ready" && ai.server === "starting") {
    text = "Loading AI model…";
  }
  if (!text) return null;
  return <span className="badge">{text}</span>;
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
