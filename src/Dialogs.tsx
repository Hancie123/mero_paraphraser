import type { ReactNode } from "react";
import type { EngineState } from "./api";

const SHORTCUTS: [string, string][] = [
  ["Paraphrase", "Ctrl+Enter"],
  ["Cancel paraphrasing", "Esc"],
  ["New", "Ctrl+N"],
  ["Open text or Word file", "Ctrl+O"],
  ["Save result", "Ctrl+S"],
  ["Copy result", "Ctrl+Shift+C"],
  ["Zoom in / out", "Ctrl+= / Ctrl+-"],
  ["Reset zoom", "Ctrl+0"],
  ["Open a menu", "Alt+F, Alt+E, Alt+V, Alt+H"],
  ["Close menu or popup", "Esc"],
];

export function Dialog({
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

export function AboutDialog({
  appVersion,
  engine,
  logFile,
  onOpenLogFolder,
  onClose,
}: {
  appVersion: string;
  engine: EngineState;
  /** Path of the engine log, when the app has one. */
  logFile: string | null;
  onOpenLogFolder: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      title="About Mero Paraphraser"
      onClose={onClose}
      actions={
        logFile ? (
          <button className="btn" onClick={onOpenLogFolder}>
            Open log folder
          </button>
        ) : undefined
      }
    >
      <p>Rewrite text offline, right on your computer. Nothing you type leaves this device.</p>
      <dl className="about-list">
        <dt>Version</dt>
        <dd>{appVersion || "…"}</dd>
        <dt>Engine</dt>
        <dd>
          {engine.state === "ready"
            ? engine.version || "Running"
            : engine.state === "starting"
              ? "Starting…"
              : "Unavailable"}
        </dd>
        {logFile && (
          <>
            <dt>Log file</dt>
            <dd className="about-path">{logFile}</dd>
          </>
        )}
        <dt>Publisher</dt>
        <dd>Mero Vision Pvt. Ltd</dd>
      </dl>
    </Dialog>
  );
}

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="Keyboard shortcuts" onClose={onClose}>
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
  );
}

/** Only shown while the engine is starting or if it failed. */
export function EngineBadge({ engine }: { engine: EngineState }) {
  if (engine.state === "ready") return null;
  if (engine.state === "starting") return <span className="badge">Starting engine…</span>;
  return (
    <span className="badge err" title={engine.message}>
      Engine unavailable
    </span>
  );
}
