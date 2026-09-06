"""The #189 pilot's training run: Unsloth QLoRA on Qwen2.5-Coder-3B-Instruct.

The recipe is the review doc's (`archive/docs/unsloth-fine-tuning-review-2026-08-06.md`
§2/§5), pinned: `unsloth==2026.8.5`, Unsloth's patched instruct checkpoint (the
pad-token fix), QLoRA r16, ChatML at training time — the same template the
serve side applies, because template mismatch is the review's documented #1
cause of post-export gibberish. Loss is computed on assistant tokens only:
the prompt is the orchestrator's text, not behaviour to learn.

Runs on the trainer rig (rig_b, RTX 3060 12 GB — rig_a must not train; see the
review's rejected-alternatives table). Input is `build_dataset.py`'s output;
output is a merged 16-bit checkpoint for the GGUF export step.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="base checkpoint path")
    parser.add_argument("--data", type=Path, required=True, help="dataset dir")
    parser.add_argument("--out", type=Path, required=True, help="output dir")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-seq", type=int, default=2048)
    args = parser.parse_args()

    from unsloth import FastLanguageModel  # first on purpose: patches trl/transformers

    # isort: split
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer
    from unsloth.chat_templates import train_on_responses_only

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0.0,
        bias="none",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    data = load_dataset(
        "json",
        data_files={
            "train": str(args.data / "train.jsonl"),
            "val": str(args.data / "val.jsonl"),
        },
    )

    def to_text(example: dict[str, Any]) -> dict[str, Any]:
        return {
            "text": tokenizer.apply_chat_template(
                example["messages"], tokenize=False, add_generation_prompt=False
            )
        }

    data = data.map(to_text, remove_columns=["messages"])

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=data["train"],
        eval_dataset=data["val"],
        args=SFTConfig(
            dataset_text_field="text",
            max_seq_length=args.max_seq,
            output_dir=str(args.out / "checkpoints"),
            per_device_train_batch_size=2,
            gradient_accumulation_steps=8,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            lr_scheduler_type="linear",
            warmup_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            bf16=True,
            logging_steps=5,
            eval_strategy="steps",
            eval_steps=20,
            save_strategy="no",
            seed=3407,
            report_to="none",
        ),
    )
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )
    result = trainer.train()
    print("train_loss:", result.training_loss)
    print("final_eval:", trainer.evaluate())

    merged = args.out / "merged16"
    model.save_pretrained_merged(str(merged), tokenizer, save_method="merged_16bit")
    print("merged checkpoint at", merged)


if __name__ == "__main__":
    main()
