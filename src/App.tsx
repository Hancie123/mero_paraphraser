import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  CANCELLED,
  cancelEngine,
  cleanDocx,
  engineStatus,
  exportDocx,
  fromBase64,
  logPath,
  MAX_CHARS,
  MODES,
  openLogFolder,
  paraphrase,
  readDocx,
  toBase64,
  type EngineState,
  type Mode,
  type Segment,
  type Stats,
} from "./api";
import { AboutDialog, EngineBadge, ShortcutsDialog } from "./Dialogs";
import MenuBar, { type Menu } from "./MenuBar";
import Picker, { type PickerPos } from "./Picker";
import ResultPane from "./ResultPane";
import { countWords, replaceSegment } from "./text";

type DialogKind = "about" | "shortcuts" | null;

const STRENGTH_LABELS = ["Light", "Moderate", "Strong"];
const ZOOM_STEPS = [0.8, 0.9, 1, 1.1, 1.25, 1.5];

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
  const [appVersion, setAppVersion] = useState("");
  const [logFile, setLogFile] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(true);
  const [picker, setPicker] = useState<PickerPos | null>(null);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [dialog, setDialog] = useState<DialogKind>(null);
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
    getVersion()
      .then(setAppVersion)
      .catch(() => {});
    logPath()
      .then(setLogFile)
      .catch(() => {});
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
      if (e !== CANCELLED) setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [input, strength, busy]);

  const cancel = () => void cancelEngine();

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
        if (handle.name.toLowerCase().endsWith(".docx"))
          await w.write(fromBase64((await exportDocx(output)).data) as BlobPart);
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
        // Esc closes a popup first; with nothing open it cancels a running paraphrase.
        if (picker || dialog) {
          setPicker(null);
          setDialog(null);
        } else if (busy) cancel();
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

  const openPicker = (index: number, el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const x = Math.min(r.left, window.innerWidth - 240);
    setPicker({ index, x: Math.max(8, x), y: r.bottom + 6 });
  };
  const closePicker = useCallback(() => setPicker(null), []);

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
        { label: "Cancel paraphrasing", shortcut: "Esc", action: cancel, disabled: !busy },
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
                <button className="ghost" onClick={paste}>
                  Paste
                </button>
                <button className="ghost" onClick={() => setInput("")} disabled={!input}>
                  Clear
                </button>
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
              <span>
                {inputWords} words · {input.length.toLocaleString()}/{MAX_CHARS.toLocaleString()} chars
              </span>
              <div className="actions">
                {busy && (
                  <button className="ghost" onClick={cancel} title="Stop paraphrasing (Esc)">
                    Cancel
                  </button>
                )}
                <button className="primary" onClick={run} disabled={!canRun}>
                  {busy ? "Paraphrasing…" : segments.length ? "Rephrase" : "Paraphrase"}
                  <kbd>Ctrl ↵</kbd>
                </button>
              </div>
            </div>
          </div>

          <ResultPane
            segments={segments}
            stats={stats}
            output={output}
            busy={busy}
            error={error}
            notice={notice}
            highlight={highlight}
            copied={copied}
            onHighlightChange={setHighlight}
            onUseOutput={useOutput}
            onCopy={() => void copy()}
            onOpenPicker={openPicker}
          />
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

      {picker && active && <Picker pos={picker} segment={active} onChoose={choose} onClose={closePicker} />}

      {dialog === "about" && (
        <AboutDialog
          appVersion={appVersion}
          engine={engine}
          logFile={logFile}
          onOpenLogFolder={() => void openLogFolder().catch((e) => setError(String(e)))}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "shortcuts" && <ShortcutsDialog onClose={() => setDialog(null)} />}
    </div>
  );
}
