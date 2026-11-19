import { invoke } from "@tauri-apps/api/core";

export type Mode = "standard" | "academic" | "professional" | "fluent" | "simple" | "creative" | "shorten";

export const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "standard", label: "Standard", hint: "Balanced rewording that keeps the meaning" },
  { id: "academic", label: "Academic", hint: "Clear academic style for essays and papers; keeps citations and hedging" },
  { id: "professional", label: "Professional", hint: "Polished tone for work documents, no contractions" },
  { id: "fluent", label: "Fluent", hint: "Natural, everyday wording" },
  { id: "simple", label: "Simple", hint: "Plain words that are easy to read" },
  { id: "creative", label: "Creative", hint: "Bolder, more varied vocabulary" },
  { id: "shorten", label: "Shorten", hint: "Cuts wordy phrases and filler" },
];

export const MAX_CHARS = 20_000;

export interface Segment {
  text: string;
  /** Present only on changed spans. */
  original?: string;
  /** What kind of change this is: Synonym, Reworded, Shortened, Expanded, Added, Capitalization. */
  kind?: string;
  alternatives?: string[];
}

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
}

export interface ParaphraseResult {
  text: string;
  segments: Segment[];
  stats: Stats;
  report: Report;
}

export const paraphrase = (text: string, mode: Mode, strength: number, seed: number) =>
  invoke<ParaphraseResult>("paraphrase", { text, mode, strength, seed });

export const engineStatus = () => invoke<{ version: string }>("engine_status");
