<div align="center">

<img src="app-icon.svg" alt="Mero Paraphraser" width="96" height="96" />

# Mero Paraphraser

**Offline desktop paraphraser that rewrites text so it reads naturally, while keeping its facts, citations and code intact.**

![Platform](https://img.shields.io/badge/platform-Windows-0078D4)
![Tauri](https://img.shields.io/badge/Tauri-2-24C8DB?logo=tauri&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Runtime deps](https://img.shields.io/badge/engine%20dependencies-none-brightgreen)
![Version](https://img.shields.io/badge/version-0.1.0-blue)

[Features](#features) ·
[How it works](#how-it-works) ·
[Getting started](#getting-started) ·
[Building](#building-a-release) ·
[Contributing](#contributing)

</div>

---

## Overview

Mero Paraphraser is a desktop app built with **Tauri 2** (a Rust shell and a React + TypeScript UI) and a **rule-based Python engine**. Everything runs on your computer. Nothing you type leaves the device, there's no account, and there's no AI model to download.

Text goes through an eight-layer pipeline. It rewrites the prose, checks that numbers, names, negations, hedges and citations survived, and explains every change in a review panel.

## Features

| | |
|---|---|
| ✍️ **Humanize mode** | Natural, everyday rewording with varied sentence rhythm, natural connectors and contractions |
| 🎚️ **Changes slider** | Controls how much of the text is rewritten, from light edits to a thorough rewrite |
| 🔍 **Reviewable edits** | Changed words are highlighted. Click one to pick another alternative or restore the original. The **Review** tab explains what each layer did |
| 🛡️ **Fact checks** | Numbers, names, negations and hedging words ("may", "suggests") must survive, or the part is rewritten again |
| 📚 **Citation-safe** | Citations (`(Smith, 2020)`, `[3]`), quotations, links, DOIs and the reference list are kept exactly as written. No citation is ever added |
| 🧭 **Section-aware** | Prose sections such as Abstract, Introduction and Discussion are rewritten. Headings, tables, equations, Keywords, Funding, Declarations and similar sections are left untouched |
| 💻 **Code-safe** | In code blocks, only comments and docstrings are reworded. The code is checked afterwards (for Python, its syntax tree too), and the block is restored if anything changed |
| 🧹 **Plainer wording** | Stock phrases like "delve into", "plays a pivotal role" and "a myriad of" are replaced, and em dashes become ordinary punctuation |
| 👻 **Invisible-character cleanup** | Removes zero-width spaces, BOMs, soft hyphens, stray bidi controls and hidden tag characters, but keeps the joiners that Nepali, Hindi, Arabic and emoji need |
| 📄 **Word files** | Opens `.docx` files and saves results as `.docx` without document properties. *File › Remove personal info from a Word file* strips author names, dates, revision IDs and template paths from an existing document |
| ⚡ **Fast and private** | Fully offline. The engine uses only the Python standard library |

### What it won't do

It doesn't invent examples, data, opinions or citations. It doesn't add or remove hedging, insert slang, plant deliberate typos or add hidden characters. If a rewrite can't keep a part's citations intact, that part is returned unchanged.

## How it works

```
┌──────────────┐  invoke   ┌──────────────────┐  JSON lines (stdin/stdout)  ┌─────────────────────┐
│   React UI   │ ────────▶ │   Rust (Tauri)   │ ──────────────────────────▶ │    Python engine    │
│    src/      │ ◀──────── │   src-tauri/     │ ◀────────────────────────── │   python-engine/    │
└──────────────┘           └──────────────────┘                             └─────────────────────┘
```

`src-tauri/src/engine.rs` starts the engine when it's first needed, restarts it if it crashes, and closes it when the app exits. During development the app runs `python-engine/app/main.py` with your system Python. In a release build, the engine is bundled with PyInstaller as a Tauri sidecar, so users don't need Python installed.

### The eight-layer pipeline

| # | Layer | Responsibility |
|:-:|---|---|
| 1 | **Input processing** | Cleans invisible characters and line endings. Detects sections, code, tables and math (`sections.py`). Sets the reference list aside. Replaces citations, quotations, links, DOIs and code with `[[n]]` placeholder tokens |
| 2 | **Context analysis** | Detects the register (academic, professional or general), proper names, acronyms, key terms and logical relationships between ideas |
| 3 | **Semantic understanding** | Records what each part must keep: numbers, names, negations and hedges |
| 4 | **Rewriting** | The rule-based engine applies phrase rewrites, synonym swaps and contractions. It writes 2–3 drafts with different seeds |
| 5 | **Language refinement** | Fixes spacing, punctuation, doubled words, capitals and "a"/"an". Replaces stock phrases and restructures the patterns AI detectors look for |
| 6 | **Meaning validation** | Checks the Layer 3 facts and the change in length |
| 7 | **Citation validation** | Every placeholder must come back exactly once, and no new citations may appear. On the final text, citations, quotations and references must match the original exactly |
| 8 | **Final output** | Builds the highlighted change list, the per-layer report and plain-language explanations |

Layers 4–7 run on one part of the text at a time. The draft with the fewest problems and the most varied rhythm wins. A part that fails validation is rewritten once more, and if its citations still can't be preserved, it's kept unchanged.

### Human-like output

AI detectors look at how predictable the wording is, how much sentence length varies ("burstiness"), and structures that language models overuse. `app/pipeline/humanizer.py` targets the last two, without changing meaning:

- **Ranks drafts** by sentence-length variation and the AI-typical patterns it finds.
- **Removes formulaic structures**: summary openers ("Overall,"), an added closing summary, and "not only… but also".
- **Rotates stiff connectors** for natural ones with the same meaning ("Furthermore," → "On top of that,"; "However," → "That said,").
- **Varies rhythm**: splits long sentences when lengths are too even, merges "X. This shows Y" into "X, which shows Y", and drops words the reader can infer ("If it is possible" → "If possible").
- **Respects the register**: in academic text, precise words such as "robust" are kept.

## Getting started

### Prerequisites

| Tool | Version |
|---|---|
| [Node.js](https://nodejs.org/) | 20 or later |
| [pnpm](https://pnpm.io/) | latest |
| [Rust](https://rustup.rs/) | stable |
| [Python](https://www.python.org/) | 3.10 or later |

On Windows you also need the [Tauri prerequisites](https://tauri.app/start/prerequisites/): the Microsoft C++ Build Tools and WebView2.

### Run in development

```bash
git clone https://github.com/Hancie123/mero_paraphraser.git
cd mero_paraphraser
pnpm install
pnpm tauri:dev
```

To use a specific Python interpreter, set `MERO_PYTHON` to its path.

## Building a release

```bash
python -m pip install -r python-engine/requirements.txt   # once: installs PyInstaller
pnpm tauri:build
```

This does two things:

1. `scripts/build-engine.mjs` bundles the engine into `src-tauri/binaries/mero-paraphraser-engine-<target-triple>`.
2. `tauri build` adds the engine as a sidecar (`src-tauri/tauri.bundle.json`) and builds the NSIS installer.

The installer, `src-tauri/target/release/bundle/nsis/Mero Paraphraser_<version>_x64-setup.exe`, is the complete release.

## Project structure

```
mero_paraphraser/
├── src/                          # React + TypeScript UI
│   ├── App.tsx                   #   main window, editor, review panel
│   ├── MenuBar.tsx               #   File / Edit / View / Help menus
│   └── api.ts                    #   typed calls into the Rust layer
├── src-tauri/                    # Tauri 2 shell (Rust)
│   └── src/engine.rs             #   engine process manager
├── scripts/build-engine.mjs      # PyInstaller sidecar build
└── python-engine/
    ├── app/
    │   ├── main.py               # protocol loop and CLI
    │   ├── api/paraphrase.py     # request handlers
    │   ├── core/
    │   │   ├── config.py         # limits, mode, avoided words
    │   │   ├── rule_engine.py    # rule-based rewriter
    │   │   └── lexicon.py        # synonym groups and phrase tables
    │   ├── pipeline/
    │   │   ├── orchestrator.py   # runs the eight layers
    │   │   ├── input_processor.py, sections.py, code_guard.py   # 1
    │   │   ├── context_analyzer.py                              # 2
    │   │   ├── semantic_analyzer.py                             # 3
    │   │   ├── rewriting_engine.py, humanizer.py                # 4
    │   │   ├── language_refiner.py                              # 5
    │   │   ├── meaning_validator.py                             # 6
    │   │   ├── citation_validator.py                            # 7
    │   │   └── output_formatter.py                              # 8
    │   ├── data/synonyms_extra.json   # generated by tools/build_lexicon.py
    │   ├── schemas/paraphrase.py      # request and inter-layer types
    │   └── utils/                     # text, document, .docx and invisible-character helpers
    ├── tests/
    └── tools/                         # eval_humanness.py, build_lexicon.py, samples/
```

## Contributing

1. Fork the repository and create a branch: `git checkout -b feature/my-change`.
2. Make your change and add tests under `python-engine/tests/` for engine behaviour.
3. Make sure `pnpm test:engine`, `pnpm typecheck` and `cargo test` pass.
4. Open a pull request that describes what changed and why.

Bug reports and feature requests are welcome in [GitHub Issues](https://github.com/Hancie123/mero_paraphraser/issues).

---

<div align="center">

Powered by **Mero Vision Pvt. Ltd**

</div>
