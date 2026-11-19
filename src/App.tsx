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
import { AboutDialog, EngineBadge, ShortcutsDialog, WordPrefsDialog } from "./Dialogs";
import MenuBar, { type Menu } from "./MenuBar";
import Picker, { type PickerPos } from "./Picker";
import { caretAfterChange, useHistory } from "./history";
import { addTo, loadPrefs, savePrefs, type WordPrefs } from "./prefs";
import ResultPane, { type ResultView } from "./ResultPane";
import { countWords, replaceSegment } from "./text";

type DialogKind = "about" | "shortcuts" | "prefs" | null;

const STRENGTH_LABELS = ["Light", "Moderate", "Strong"];
const levelLabel = (value: number) => STRENGTH_LABELS[Math.min(2, Math.floor(value / 34))];
const ZOOM_STEPS = [0.8, 0.9, 1, 1.1, 1.25, 1.5];
const OPENABLE = /\.(txt|md|docx)$/i;

/** Typing and deleting are grouped into one undo step; paste, drop and the like are not. */
const coalesces = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
  const type = (e.nativeEvent as InputEvent).inputType ?? "";
  return type === "insertText" || type.startsWith("delete");
};

const hasFiles = (e: React.DragEvent | DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");

export default function App() {
  const history = useHistory("");
  const input = history.text;
  const setInput = history.set;
  const [source, setSource] = useState(""); // the text the current result was made from
  const [view, setView] = useState<ResultView>("edits");
  const [dragging, setDragging] = useState(false);
  const mode: Mode = "humanize";
  const [strength, setStrength] = useState(50); // how many words change
  const [restructure, setRestructure] = useState(30); // how many sentences are rebuilt
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
  const [prefs, setPrefsState] = useState<WordPrefs>(loadPrefs);
  const setPrefs = useCallback((next: WordPrefs) => {
    setPrefsState(next);
    savePrefs(next);
  }, []);
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
      const result = await paraphrase(input, mode, strength, restructure, seed, prefs);
      setSource(input);
      setSegments(result.segments);
      setStats(result.stats);
      setEngine((e) => (e.state === "ready" ? e : { state: "ready", version: "" }));
    } catch (e) {
      if (e !== CANCELLED) setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [input, strength, restructure, busy, prefs]);

  // A file dropped outside the Original box must not make the webview navigate to it.
  useEffect(() => {
    const block = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    window.addEventListener("dragover", block);
    window.addEventListener("drop", block);
    return () => {
      window.removeEventListener("dragover", block);
      window.removeEventListener("drop", block);
    };
  }, []);

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
    if (!OPENABLE.test(file.name)) {
      setError(`${file.name} can't be opened. Use a .txt, .md or .docx file.`);
      return;
    }
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

  /** Moves the caret once React has rendered `text` into the Original box. */
  const placeCaret = (pos: number) =>
    requestAnimationFrame(() => {
      const el = editorRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(pos, pos);
    });

  /** Replaces the selection in the Original box with `text` as one undo step. */
  const replaceSelection = (text: string) => {
    const el = editorRef.current;
    if (!el) return;
    const { selectionStart: start, selectionEnd: end } = el;
    const next = (input.slice(0, start) + text + input.slice(end)).slice(0, MAX_CHARS);
    setInput(next);
    placeCaret(Math.min(start + text.length, next.length));
  };

  const undoInput = () => {
    if (!history.canUndo) return;
    const target = history.peek.undo;
    history.undo();
    placeCaret(caretAfterChange(input, target));
  };
  const redoInput = () => {
    if (!history.canRedo) return;
    const target = history.peek.redo;
    history.redo();
    placeCaret(caretAfterChange(input, target));
  };

  /** Runs an editing command on the Original text box (Clipboard API; no document.execCommand). */
  const edit = async (command: "undo" | "redo" | "cut" | "copy" | "selectAll") => {
    const el = editorRef.current;
    if (!el) return;
    el.focus();
    if (command === "selectAll") return el.select();
    if (command === "undo") return undoInput();
    if (command === "redo") return redoInput();
    const selected = input.slice(el.selectionStart, el.selectionEnd);
    if (!selected) return;
    try {
      await navigator.clipboard.writeText(selected);
      if (command === "cut") replaceSelection("");
    } catch {
      setError(`Clipboard access was blocked. Use Ctrl+${command === "cut" ? "X" : "C"} instead.`);
    }
  };

  const pasteIntoEditor = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) replaceSelection(text);
    } catch {
      setError("Clipboard access was blocked. Paste with Ctrl+V instead.");
    }
  };

  /* ---------- drag and drop onto the Original box ---------- */

  const onDragOver = (e: React.DragEvent) => {
    if (!hasFiles(e)) return; // dragged text: let the textarea handle it
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDragging(true);
  };
  const onDragLeave = (e: React.DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
  };
  const onDrop = (e: React.DragEvent) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    setDragging(false);
    void onFileChosen(e.dataTransfer.files[0]);
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
      if (!ctrl || e.altKey || dialog) return; // a dialog is modal: no app shortcuts behind it
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

  // From the picker: remember the choice for next time, and undo this change now.
  const keepWord = (word: string) => {
    setPrefs({ ...prefs, locked: addTo(prefs.locked, word) });
    choose(word);
    setNotice(`“${word}” will be kept as written from now on (Edit › Word preferences).`);
  };
  const banWord = (word: string) => {
    if (!picker) return;
    setPrefs({ ...prefs, banned: addTo(prefs.banned, word) });
    choose(segments[picker.index].original ?? word);
    setNotice(`“${word}” won’t be used from now on (Edit › Word preferences).`);
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
        { label: "Undo", shortcut: "Ctrl+Z", action: () => void edit("undo"), disabled: !history.canUndo },
        { label: "Redo", shortcut: "Ctrl+Y", action: () => void edit("redo"), disabled: !history.canRedo },
        { separator: true },
        { label: "Cut", shortcut: "Ctrl+X", action: () => void edit("cut") },
        { label: "Copy", shortcut: "Ctrl+C", action: () => void edit("copy") },
        { label: "Paste", shortcut: "Ctrl+V", action: () => void pasteIntoEditor() },
        { label: "Select all", shortcut: "Ctrl+A", action: () => void edit("selectAll") },
        { separator: true },
        { label: "Paraphrase", shortcut: "Ctrl+Enter", action: () => void run(), disabled: !canRun },
        { label: "Cancel paraphrasing", shortcut: "Esc", action: cancel, disabled: !busy },
        { label: "Copy result", shortcut: "Ctrl+Shift+C", action: () => void copy(), disabled: !output },
        { label: "Use result as input", action: useOutput, disabled: !output },
        { separator: true },
        { label: "Word preferences…", action: () => setDialog("prefs") },
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
          {[
            { label: "Words", hint: "How many words and phrases are swapped", value: strength, set: setStrength },
            {
              label: "Sentences",
              hint: "How many sentences are rebuilt: clauses moved, active/passive, merged or shortened",
              value: restructure,
              set: setRestructure,
            },
          ].map((s) => (
            <label className="strength" key={s.label} title={s.hint}>
              <span>{s.label}</span>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={s.value}
                aria-label={`${s.label}: ${s.hint}`}
                style={{ "--pct": `${s.value}%` } as CSSProperties}
                onChange={(e) => s.set(Number(e.target.value))}
              />
              <span className="strength-label">{s.value === 0 ? "Off" : levelLabel(s.value)}</span>
            </label>
          ))}
        </section>

        <main className="panes">
          <div
            className={dragging ? "pane dropping" : "pane"}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            {dragging && (
              <div className="drop-hint" aria-hidden="true">
                Drop a .txt, .md or .docx file to open it
              </div>
            )}
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
              onChange={(e) => setInput(e.target.value, coalesces(e))}
              onKeyDown={(e) => {
                // Our own history: the browser's undo stack doesn't track React's updates.
                if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
                const k = e.key.toLowerCase();
                if (k === "z" && !e.shiftKey) {
                  e.preventDefault();
                  undoInput();
                } else if (k === "y" || (k === "z" && e.shiftKey)) {
                  e.preventDefault();
                  redoInput();
                }
              }}
              placeholder="Type, paste or drop a file with the text you want to paraphrase…"
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
            source={source}
            view={view}
            onViewChange={setView}
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

      {picker && active && (
        <Picker
          pos={picker}
          segment={active}
          onChoose={choose}
          onKeep={keepWord}
          onBan={banWord}
          onClose={closePicker}
        />
      )}

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
      {dialog === "prefs" && <WordPrefsDialog prefs={prefs} onSave={setPrefs} onClose={() => setDialog(null)} />}
    </div>
  );
}
