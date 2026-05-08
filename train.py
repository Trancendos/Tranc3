#!/usr/bin/env python3
# train.py — TRANC3 Fine-tuning Pipeline
# Fine-tunes phi-3-mini on TRANC3 personality profiles
# Zero cost: runs on HuggingFace ZeroGPU or local GPU

import os
import logging
import argparse
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tranc3.train")


def parse_args():
    p = argparse.ArgumentParser(description="Fine-tune TRANC3 model")
    p.add_argument("--base-model",  default="microsoft/phi-3-mini-4k-instruct")
    p.add_argument("--output-dir",  default="./models/tranc3-base")
    p.add_argument("--data-dir",    default="./data")
    p.add_argument("--epochs",      type=int,   default=3)
    p.add_argument("--batch-size",  type=int,   default=4)
    p.add_argument("--lr",          type=float, default=2e-4)
    p.add_argument("--max-length",  type=int,   default=512)
    p.add_argument("--lora",        action="store_true", default=True)
    p.add_argument("--lora-r",      type=int,   default=16)
    p.add_argument("--lora-alpha",  type=int,   default=32)
    p.add_argument("--languages",   default="en,es,fr,de,zh,ja")
    return p.parse_args()


def train(args):
    try:
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer,
            TrainingArguments, Trainer, DataCollatorForLanguageModeling
        )
        import torch
    except ImportError:
        logger.error("Install transformers: pip install transformers torch")
        return

    logger.info(f"Loading base model: {args.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model with optional LoRA
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        trust_remote_code=True,
        device_map="auto" if torch.cuda.is_available() else None,
    )

    if args.lora:
        try:
            from peft import get_peft_model, LoraConfig, TaskType
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=args.lora_r,
                lora_alpha=args.lora_alpha,
                target_modules=["q_proj", "v_proj"],
                lora_dropout=0.05,
                bias="none",
            )
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
            logger.info("LoRA applied")
        except ImportError:
            logger.warning("peft not installed — training full model (slow). Install: pip install peft")

    # Dataset
    from src.core.dataset import MultilingualDataset
    languages = args.languages.split(",")
    train_dataset = MultilingualDataset(
        tokenizer=tokenizer,
        data_dir=args.data_dir,
        max_length=args.max_length,
        languages=languages,
        split="train",
    )
    logger.info(f"Training samples: {len(train_dataset)}")

    # Training arguments
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.lr,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        report_to="none",
        dataloader_num_workers=0,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    logger.info("Starting training...")
    trainer.train()

    # Save
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    logger.info(f"Model saved to {output_dir}")
    logger.info("Set MODEL_PATH={output_dir} in .env to use this model")


if __name__ == "__main__":
    args = parse_args()
    train(args)
