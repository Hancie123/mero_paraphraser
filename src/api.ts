import { invoke } from "@tauri-apps/api/core";

export type Mode = "humanize";

export const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "humanize", label: "Humanize", hint: "Natural, human-sounding rewording that keeps the meaning" },
];

export const MAX_CHARS = 20_000;

export interface Segment {
  text: string;
  /** Present only on changed spans. */
  original?: string;
  /** What kind of change this is: Synonym, Reworded, Shortened, Expanded, Added, Capitalization. */
  kind?: string;
  alternatives?: string[];
  /** How big the change is, for colour-coded highlighting. */
  level?: ChangeLevel;
}

export type ChangeLevel = "word" | "phrase" | "sentence" | "added";

/** One of the eight processing layers, as reported by the engine. */
export interface LayerReport {
  id: string;
  name: string;
  status: "ok" | "warning";
  detail: string;
}

export interface Report {
  layers: LayerReport[];
  explanations: string[];
  warnings: string[];
  register: "academic" | "professional" | "general";
}

export interface Stats {
  words_in: number;
  words_out: number;
  changes: number;
  change_pct: number;
  /** Number of highlighted changes of each level. */
  levels?: Record<ChangeLevel, number>;
}

export interface ParaphraseResult {
  text: string;
  segments: Segment[];
  stats: Stats;
  report: Report;
}

export const paraphrase = (text: string, mode: Mode, strength: number, seed: number) =>
  invoke<ParaphraseResult>("paraphrase", { text, mode, strength, seed });

export const exportDocx = (text: string) => invoke<{ data: string }>("export_docx", { text });
export const readDocx = (data: string) => invoke<{ text: string }>("read_docx", { data });
export const cleanDocx = (data: string) => invoke<{ data: string; removed: string[] }>("clean_docx", { data });

/** Base64 helpers for passing .docx files to the engine. */
export function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

export function fromBase64(data: string): Uint8Array {
  const bin = atob(data);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export const engineStatus = () => invoke<{ version: string }>("engine_status");

export type EngineState =
  { state: "starting" } | { state: "ready"; version: string } | { state: "error"; message: string };

/** The error a request rejects with after `cancelEngine` (matches `engine::CANCELLED`). */
export const CANCELLED = "Cancelled.";
/** Stops the request in flight; the engine restarts for the next one. */
export const cancelEngine = () => invoke<void>("cancel_engine");
/** Where the engine writes its log (release builds), if anywhere. */
export const logPath = () => invoke<string | null>("log_path");
export const openLogFolder = () => invoke<void>("open_log_folder");
