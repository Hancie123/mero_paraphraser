"""Mero Paraphraser engine process.

Protocol (used by the Tauri app): one JSON request per line on stdin, one JSON
response per line on stdout.

    -> {"id": 1, "cmd": "paraphrase", "text": "...", "mode": "humanize", "strength": 50, "seed": 7}
    <- {"id": 1, "ok": true, "result": {"text": ..., "segments": [...], "stats": {...}, "report": {...}}}
    <- {"id": 1, "ok": false, "error": "..."}

Other commands: ping, export_docx {text} -> {data}, read_docx {data} -> {text},
clean_docx {data} -> {data, removed}. ``data`` is a base64-encoded .docx file.
The process exits when stdin closes, so it never outlives the app.

For quick manual testing:
    python python-engine/app/main.py --text "Some text"
    python python-engine/app/main.py --file paper.docx --out result.docx
    python python-engine/app/main.py --clean-docx in.docx --out clean.docx
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the "app" package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.paraphrase import handle, paraphrase  # noqa: E402
from app.schemas.paraphrase import ParaphraseError  # noqa: E402


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
            traceback.print_exc()  # stderr goes to engine.log in release builds
            resp = {"id": rid, "ok": False, "error": f"internal engine error: {exc}"}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Mero Paraphraser engine")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--file", help="a .txt, .md or .docx file to paraphrase")
    src.add_argument("--clean-docx", metavar="DOCX", help="remove personal metadata from a .docx (needs --out)")
    parser.add_argument("--out", help="write the result here (.docx or text)")
    parser.add_argument("--strength", type=int, default=50)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--report", action="store_true", help="also print the eight-layer report")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    from app.utils.docx import build_docx, clean_docx, read_docx

    if args.clean_docx:
        if not args.out:
            parser.error("--clean-docx needs --out")
        blob, removed = clean_docx(Path(args.clean_docx).read_bytes())
        Path(args.out).write_bytes(blob)
        print("\n".join(removed))
        return
    text = args.text
    if args.file:
        path = Path(args.file)
        text = read_docx(path.read_bytes()) if path.suffix.lower() == ".docx" else path.read_text(encoding="utf-8-sig")
    result = paraphrase({"text": text, "strength": args.strength, "seed": args.seed})
    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".docx":
            out.write_bytes(build_docx(result["text"]))
        else:
            out.write_text(result["text"], encoding="utf-8")
    else:
        print(result["text"])
    if args.report:
        print()
        for layer in result["report"]["layers"]:
            print(f"[{layer['status']:>7}] {layer['name']}: {layer['detail']}")
        for line in result["report"]["explanations"]:
            print(f"  - {line}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli(sys.argv[1:])
    else:
        serve()
