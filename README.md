# TRANC3 — Core AI Platform

A custom transformer-based AI built from the ground up in PyTorch.
Owned entirely by you. No API wrappers. No hosted dependencies.

---

## What This Is

A decoder-only transformer language model — the same architectural family as GPT — built from PyTorch primitives. It has a real training pipeline, a real tokenizer, and a personality matrix system that lets you deploy different agent personas from a single trained model.

The model is designed to be compassionate, capable, and honest. The two included personality profiles are `tranc3-base` (empathetic companion) and `tranc3-builder` (technical assistant). More can be added as JSON files without touching any code.

---

## Architecture

- **Model**: Decoder-only transformer with RoPE positional embeddings and SwiGLU activation
- **Tokenizer**: SentencePiece BPE, trained on your data, 32k vocabulary
- **Personality layer**: JSON profile system injected at inference time
- **Training**: AdamW, cosine LR schedule, gradient accumulation, mixed precision

Model sizes available:

| Size   | Parameters | Hardware       |
|--------|-----------|----------------|
| small  | ~10M      | CPU feasible   |
| medium | ~50M      | GPU recommended|
| large  | ~150M     | Slough-grade   |

---

## Setup (Docker on Windows)

```bash
# Clone or copy this directory into your Ubuntu Docker container

# Build the container
cd docker
docker compose build

# Or run directly in your Ubuntu environment
pip install -r requirements.txt
```

---

## Step-by-Step: First Run

### Step 1 — Prepare training data
```bash
python scripts/prepare_data.py
```
Downloads EmpatheticDialogues and DailyDialog automatically.
To add your own data: place JSONL files in `data/raw/custom/`
Format: `{"turns": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}`

### Step 2 — Train the tokenizer
```bash
python scripts/train_tokenizer.py
```

### Step 3 — Train the model
```bash
# CPU / testing (small model)
python scripts/train.py --size small --max_steps 5000

# GPU (medium model, full training)
python scripts/train.py --size medium
```

### Step 4 — Chat
```bash
python scripts/chat.py --profile tranc3-base
python scripts/chat.py --profile tranc3-builder
```

---

## Adding a Personality

Create a new JSON file in `src/personality/profiles/`:

```json
{
  "name": "tranc3-myagent",
  "version": "1.0.0",
  "system_prompt": "Your character definition here.",
  "temperature": 0.75,
  "top_k": 50,
  "top_p": 0.90,
  "repetition_penalty": 1.12,
  "max_new_tokens": 512,
  "tone": "warm",
  "domain_focus": "your-domain",
  "avatar_id": null
}
```

It will be available immediately — no restart, no retraining.

---

## Project Structure

```
tranc3/
├── src/
│   ├── core/
│   │   ├── model.py          Transformer architecture
│   │   ├── tokenizer.py      BPE tokenizer
│   │   └── config.py         All configuration
│   ├── training/
│   │   ├── trainer.py        Training loop
│   │   └── dataset.py        Data loading
│   ├── personality/
│   │   ├── matrix.py         Personality engine
│   │   └── profiles/         JSON personality files
│   └── inference/
│       └── engine.py         Runtime inference + CLI
├── scripts/
│   ├── prepare_data.py       Download + format training data
│   ├── train_tokenizer.py    Train the tokenizer
│   ├── train.py              Train the model
│   └── chat.py               Local chat interface
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── data/                     Training data (gitignored)
├── models/                   Saved checkpoints (gitignored)
└── requirements.txt
```

---

## Roadmap

- [ ] Phase 1: Local core (this codebase)
- [ ] Phase 2: Governance layer (TIGA integration)
- [ ] Phase 3: Cloud deployment (provider-agnostic worker interface)
- [ ] Phase 4: Avatar bridge API

---

## Notes

Model weights and training data are excluded from version control.
The architecture, training pipeline, and personality system are yours permanently.
