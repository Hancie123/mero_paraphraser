"""Fine-tune the paraphrasing model to write like a person by default (DPO + LoRA).

Every time the pipeline writes several drafts, the one it ships (it passed the
meaning check and scored most human) and the one that scored least human make a
preference pair. Collect pairs while using the app, then train on them:

    1. Collect (any number of sessions; the file keeps growing):
         set MERO_COLLECT_PREFS=%USERPROFILE%\\mero-prefs.jsonl      (PowerShell: $env:MERO_COLLECT_PREFS=...)
         pnpm tauri dev     or     python python-engine/tools/eval_humanness.py --modes standard fluent academic
       A few hundred pairs is a sensible minimum; more varied text is better than more of the same.

    2. Train (needs an NVIDIA GPU with ~16 GB, or a rented one; CPU is far too slow):
         pip install -r python-engine/tools/requirements-train.txt
         python python-engine/tools/train_dpo.py --data %USERPROFILE%\\mero-prefs.jsonl --out mero-dpo

    3. Convert to GGUF and quantize with llama.cpp (https://github.com/ggml-org/llama.cpp):
         python llama.cpp/convert_hf_to_gguf.py mero-dpo/merged --outtype f16 --outfile mero-dpo-f16.gguf
         llama-quantize mero-dpo-f16.gguf model.gguf Q4_K_M

    4. Try it: put model.gguf in python-engine/models/ (the engine prefers it over the installed model)
       and compare with tools/eval_humanness.py. To ship it, update MODEL in app/core/config.py
       (URL, SHA-256, size) and MERO_AI_MODEL_FILE in src-tauri/windows/hooks.nsh.

Pairs whose drafts differ only slightly teach little; --min-margin drops them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"  # same model as the shipped GGUF


def load_pairs(path: Path, min_margin: float) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        scores = r.get("scores", {})
        if scores.get("chosen", 0) - scores.get("rejected", 0) < min_margin:
            continue
        rows.append({
            "prompt": [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["prompt"]}],
            "chosen": [{"role": "assistant", "content": r["chosen"]}],
            "rejected": [{"role": "assistant", "content": r["rejected"]}],
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="JSON lines written via MERO_COLLECT_PREFS")
    parser.add_argument("--out", type=Path, default=Path("mero-dpo"))
    parser.add_argument("--base", default=BASE_MODEL)
    parser.add_argument("--min-margin", type=float, default=0.15)
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--beta", type=float, default=0.1, help="lower = move further from the base model")
    args = parser.parse_args()

    # Heavy imports here so --help works without the training packages.
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import DPOConfig, DPOTrainer

    pairs = load_pairs(args.data, args.min_margin)
    if len(pairs) < 50:
        raise SystemExit(f"only {len(pairs)} usable pairs in {args.data}; collect more first (see --help)")
    print(f"Training on {len(pairs)} preference pairs")
    split = Dataset.from_list(pairs).train_test_split(test_size=0.1, seed=0)

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16, device_map="auto")
    config = DPOConfig(
        output_dir=str(args.out),
        beta=args.beta,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=5e-6,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        bf16=True,
        gradient_checkpointing=True,
        max_length=3072,
        max_prompt_length=2048,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        report_to="none",
    )
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    trainer = DPOTrainer(model=model, args=config, train_dataset=split["train"], eval_dataset=split["test"],
                         processing_class=tokenizer, peft_config=lora)
    trainer.train()

    merged = trainer.model.merge_and_unload()
    merged.save_pretrained(args.out / "merged", safe_serialization=True)
    tokenizer.save_pretrained(args.out / "merged")
    print(f"Merged model saved to {args.out / 'merged'}; convert it to GGUF next (see --help)")


if __name__ == "__main__":
    main()
