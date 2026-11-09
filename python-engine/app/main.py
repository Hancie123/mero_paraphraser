"""Mero Paraphraser engine process.

Protocol (used by the Tauri app): one JSON request per line on stdin, one JSON
response per line on stdout.

    -> {"id": 1, "cmd": "paraphrase", "text": "...", "mode": "academic", "strength": 50, "seed": 7, "engine": "auto"}
    <- {"id": 1, "ok": true, "result": {"text": ..., "segments": [...], "stats": {...}, "report": {...}}}
    <- {"id": 1, "ok": false, "error": "..."}

Other commands: ping, ai_status, ai_download, ai_cancel, ai_remove, ai_warm.
The process exits when stdin closes, so it never outlives the app.

Release builds run  python python-engine/app/main.py --prepare-ai  to fetch and verify the model.

For quick manual testing:
    python python-engine/app/main.py --mode academic --engine ai --text "Some text"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the "app" package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.paraphrase import handle, model_manager, paraphrase  # noqa: E402
from app.core.config import MODES  # noqa: E402
from app.schemas.paraphrase import ENGINES, ParaphraseError  # noqa: E402


def serve() -> None:
    sys.stdin.reconfigure(encoding="utf-8-sig")  # tolerate a leading BOM
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            resp = {"id": rid, "ok": True, "result": handle(req)}
        except ParaphraseError as exc:
            resp = {"id": rid, "ok": False, "error": str(exc)}
        except Exception as exc:  # keep serving; report the failure to the app
            resp = {"id": rid, "ok": False, "error": f"internal engine error: {exc}"}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def prepare_ai() -> None:
    """Download and verify the AI model for packaging; prints the folder it is in."""
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        folder = model_manager.prepare(lambda msg: print(msg, file=sys.stderr, flush=True))
    except ParaphraseError as exc:
        sys.exit(f"error: {exc}")
    print(folder)


def cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Mero Paraphraser engine")
    parser.add_argument("--text", required=True)
    parser.add_argument("--mode", default="standard", choices=list(MODES))
    parser.add_argument("--strength", type=int, default=50)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--engine", default="basic", choices=ENGINES)
    parser.add_argument("--report", action="store_true", help="also print the eight-layer report")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    result = paraphrase({"text": args.text, "mode": args.mode, "strength": args.strength,
                         "seed": args.seed, "engine": args.engine})
    print(result["text"])
    if args.report:
        print()
        for layer in result["report"]["layers"]:
            print(f"[{layer['status']:>7}] {layer['name']}: {layer['detail']}")
        for line in result["report"]["explanations"]:
            print(f"  - {line}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--prepare-ai"]:
        prepare_ai()
    elif len(sys.argv) > 1:
        cli(sys.argv[1:])
    else:
        serve()
