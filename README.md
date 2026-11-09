# Mero Paraphraser

An offline desktop paraphrasing tool built with **Tauri 2** (Rust + React/TypeScript UI) and a **Python** engine that runs a local AI model.

## Features

- Seven modes: **Standard**, **Academic**, **Professional**, **Fluent**, **Simple**, **Creative**, **Shorten**
- A "Changes" slider that controls how much text is rewritten
- An eight-layer pipeline that protects citations, quotations and references, checks that the meaning didn't change, and explains what it changed (the **Review** tab)
- Changed words are highlighted. Click one to pick another alternative or go back to the original.
- Offline AI model (Qwen3 4B Instruct, Apache 2.0). A rule-based engine is used until the model is installed.
- Runs fully offline. The engine uses only the Python standard library.

## Architecture

```
React UI  ──invoke──▶  Rust (src-tauri)  ──JSON lines over stdin/stdout──▶  Python engine (python-engine/)
                                                                              └─ llama-server (local model)
```

```
python-engine/
├── app/
│   ├── main.py                  # engine process: protocol loop, CLI, --prepare-ai
│   ├── api/paraphrase.py        # request handlers (paraphrase, ping, ai_*)
│   ├── core/
│   │   ├── config.py            # limits, modes, pinned model downloads, folders
│   │   ├── model_manager.py     # download + verify the model, run llama-server, completions
│   │   ├── rule_engine.py       # rule-based fallback rewriter
│   │   └── lexicon.py           # its synonym and phrase tables
│   ├── pipeline/
│   │   ├── orchestrator.py      # ParaphrasePipeline: runs the eight layers
│   │   ├── input_processor.py   # 1
│   │   ├── context_analyzer.py  # 2
│   │   ├── semantic_analyzer.py # 3
│   │   ├── rewriting_engine.py  # 4
│   │   ├── language_refiner.py  # 5
│   │   ├── meaning_validator.py # 6
│   │   ├── citation_validator.py# 7
│   │   └── output_formatter.py  # 8
│   ├── prompts/                 # system, judge and one prompt per mode
│   ├── schemas/paraphrase.py    # request and inter-layer data types
│   └── utils/                   # text_utils.py, document_utils.py
├── models/                      # optional model.gguf for development
├── tests/
└── requirements.txt             # PyInstaller (build only)
```

- `src-tauri/src/engine.rs` starts the engine on demand, restarts it if it crashes, and stops it on exit.
- `src/` is the React UI.

In **dev** the app runs `python-engine/app/main.py` with your system Python (set `MERO_PYTHON` to use a different interpreter).
In **release** the engine is bundled with PyInstaller and shipped as a Tauri sidecar, so users don't need Python installed.

## The eight layers

| # | Layer | What it does |
|---|---|---|
| 1 | Input processing | Cleans invisible characters and line endings, splits paragraphs, sets a trailing reference list aside, and replaces citations (`(Smith, 2020)`, `Smith et al. (2020)`, `[3]`), direct quotations, links, DOIs and code with `[[n]]` tokens |
| 2 | Context analysis | Detects the register (academic, professional, general), proper names and acronyms, repeated key terms, and logical relationships (contrast, cause and effect…) |
| 3 | Semantic understanding | Lists what each part must keep: numbers, names, negations and hedges ("may", "suggests") |
| 4 | AI rewriting | Rewrites a few paragraphs at a time with the mode's prompt plus what layers 2 and 3 found |
| 5 | Language refinement | Fixes spacing, punctuation, doubled words, sentence capitals and "a"/"an", and replaces stock AI phrases the author didn't use |
| 6 | Meaning validation | Checks the facts from layer 3, then has the model list added, missing or changed details and score the rewrite from 1 to 5 |
| 7 | Citation validation | Every token must come back exactly once and no new citations may appear; on the final text, every citation, quotation and the reference list must be verbatim |
| 8 | Final output | Highlights each change with its kind (synonym, reworded, shortened…), and builds the per-layer report and explanations shown in the Review tab |

A part that fails layer 6 or 7 is rewritten once more with the problems as feedback. If its citations still can't be preserved, it is kept unchanged. Layers 2, 3 and 5 are rule-based on purpose, because each extra model call costs several seconds on a CPU. Expect roughly 15–40 seconds per few paragraphs on a typical laptop CPU, including validation.

The meaning check (layer 6) runs on the same 4B model. It catches most changes in meaning, but not all of them, so review the result for anything important.

## AI model

The model and runtime are two pinned, SHA-256-verified files, about 2.5 GB in total, stored in `%LOCALAPPDATA%\com.merovision.paraphraser\ai`. The uninstaller's "Delete the application data" option removes that folder.

How the model gets there:

- **Release:** `pnpm tauri:build` creates `release/Mero Paraphraser <version>/` containing the installer and an `ai\` folder. The post-install hook in `src-tauri/windows/hooks.nsh` copies `ai\` into the data folder, so installation works offline. Zip and ship the whole folder. The model can't be put inside the installer because NSIS installers are limited to 2 GB.
- **Otherwise** (development, or running the installer without the `ai\` folder): the app downloads the model automatically on first launch and uses the rule-based engine until the download finishes.
- **Development:** a model placed at `python-engine/models/model.gguf` is used instead of the installed one.

`llama-server` runs on a random localhost port and is placed in a Windows job object, so it is closed even if the engine is killed.

Overrides: `MERO_AI_HOME` (data folder), `MERO_LLAMA_SERVER` (path to `llama-server`) and `MERO_AI_MODEL` (path to a `.gguf`).

To upgrade the model or runtime, change `RUNTIME` / `MODEL` in `app/core/config.py`. Update the URL, SHA-256 and size together, and update `MERO_AI_MODEL_FILE` in `hooks.nsh`.

## Requirements

Node 20+, pnpm, Rust (stable), Python 3.10+

## Development

```bash
pnpm install
pnpm tauri:dev
```

Test the engine on its own:

```bash
pnpm test:engine
python python-engine/app/main.py --prepare-ai      # download and verify the model
python python-engine/app/main.py --engine ai --mode academic --report --text "I don't think it's a big problem."
```

## Release build

```bash
python -m pip install -r python-engine/requirements.txt   # once (PyInstaller)
pnpm tauri:build
```

`tauri:build` does three things:

1. `scripts/build-engine.mjs` builds the engine, with its prompt files, into `src-tauri/binaries/mero-paraphraser-engine-<target-triple>`.
2. `tauri build` runs with `src-tauri/tauri.bundle.json`, which adds the engine sidecar and builds the NSIS installer.
3. `scripts/package-release.mjs` assembles `release/Mero Paraphraser <version>/` with the installer and the AI model.

## Customizing

- **Prompts:** edit the files in `python-engine/app/prompts/`. `system.txt` holds the rules for every rewrite, `judge.txt` is the meaning check, and each mode has its own file.
- **Rule-based vocabulary:** add synonym groups to `GROUPS` in `python-engine/app/core/lexicon.py`. Use `keys` to list only the words that are safe to replace. If a word is ambiguous (for example "show" can be a noun), list it only as a replacement. Run `pnpm test:engine` after editing; it catches duplicate keys.

---

Powered by Mero Vision Pvt. Ltd
