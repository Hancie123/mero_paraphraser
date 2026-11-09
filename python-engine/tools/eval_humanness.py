"""Measure how human the paraphraser's output reads, before and after a change.

Runs every passage in tools/samples/*.txt (or the folder given with --samples)
through the pipeline and reports, per mode:

* local metrics: sentence-length variation (burstiness), AI-typical patterns
  found, and the human score the pipeline itself computed;
* the meaning-check pass rate, so you can see when "more human" starts to cost accuracy;
* GPTZero's verdict, if GPTZERO_API_KEY is set (paid API; the text is sent to
  GPTZero's servers, so only use passages you're allowed to share).

    python python-engine/tools/eval_humanness.py --modes standard academic --engine ai
    python python-engine/tools/eval_humanness.py --out results.json   # keep a record to compare later

Detectors change often: re-run this after GPTZero updates, not just after code changes.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.paraphrase import paraphrase  # noqa: E402
from app.pipeline.humanizer import ai_patterns, burstiness  # noqa: E402

GPTZERO_URL = "https://api.gptzero.me/v2/predict/text"


def gptzero(text: str, key: str) -> dict | None:
    """GPTZero's class probabilities for ``text`` ({"human": .., "ai": .., "mixed": ..}), or None."""
    req = urllib.request.Request(
        GPTZERO_URL,
        data=json.dumps({"document": text}).encode(),
        headers={"x-api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            doc = (json.load(r).get("documents") or [{}])[0]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  GPTZero request failed: {exc}", file=sys.stderr)
        return None
    probs = doc.get("class_probabilities") or {}
    return {
        "human": probs.get("human"),
        "ai": probs.get("ai", doc.get("completely_generated_prob")),
        "mixed": probs.get("mixed"),
        "class": doc.get("predicted_class"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, default=Path(__file__).with_name("samples"))
    parser.add_argument("--modes", nargs="+", default=["standard"])
    parser.add_argument("--strength", type=int, default=60)
    parser.add_argument("--engine", default="ai", choices=["ai", "basic", "auto"])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, help="write all results as JSON")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    key = os.environ.get("GPTZERO_API_KEY", "")
    files = sorted(args.samples.glob("*.txt"))
    if not files:
        sys.exit(f"no .txt passages in {args.samples}")
    rows = []
    for mode in args.modes:
        for f in files:
            source = f.read_text(encoding="utf-8").strip()
            t = time.time()
            result = paraphrase({"text": source, "mode": mode, "strength": args.strength,
                                 "seed": args.seed, "engine": args.engine})
            report = result["report"]
            row = {
                "file": f.name,
                "mode": mode,
                "seconds": round(time.time() - t, 1),
                "burstiness_in": round(burstiness(source), 2),
                "burstiness_out": round(burstiness(result["text"]), 2),
                "patterns_in": ai_patterns(source),
                "patterns_out": ai_patterns(result["text"]),
                "human_score": report.get("humanness", {}).get("score"),
                "meaning_ok": not report["warnings"],
                "warnings": report["warnings"],
                "output": result["text"],
            }
            if key:
                row["gptzero_in"] = gptzero(source, key)
                row["gptzero_out"] = gptzero(result["text"], key)
            rows.append(row)
            gz = ""
            if key and row["gptzero_out"]:
                gz = f"  GPTZero human {row['gptzero_in'] and row['gptzero_in']['human']} -> {row['gptzero_out']['human']}"
            print(f"[{mode}] {f.name}: burstiness {row['burstiness_in']} -> {row['burstiness_out']}, "
                  f"patterns {len(row['patterns_in'])} -> {len(row['patterns_out'])}, "
                  f"human score {row['human_score']}, meaning {'ok' if row['meaning_ok'] else 'WARN'}, "
                  f"{row['seconds']}s{gz}")

    print("\nSummary")
    for mode in args.modes:
        mine = [r for r in rows if r["mode"] == mode]
        line = (f"  {mode}: meaning ok {sum(r['meaning_ok'] for r in mine)}/{len(mine)}, "
                f"burstiness {statistics.fmean(r['burstiness_out'] for r in mine):.2f}, "
                f"patterns/passage {statistics.fmean(len(r['patterns_out']) for r in mine):.1f}")
        scored = [r["gptzero_out"]["human"] for r in mine if r.get("gptzero_out") and r["gptzero_out"]["human"] is not None]
        if scored:
            line += f", GPTZero rated human {sum(h >= 0.5 for h in scored)}/{len(scored)} (mean {statistics.fmean(scored):.2f})"
        print(line)
    if args.out:
        args.out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
