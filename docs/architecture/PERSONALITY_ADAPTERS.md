# Personality Trait Adapters — Training Pipeline (QLoRA + DPO/ORPO)

**Status**: Design for v0.9.0 foundation  
**Goal**: Produce the first 2–3 trait adapters that can be loaded behind the existing JSON personality system.

---

## 1. Design Principles

- Keep the current **JSON personality profiles** as the primary user-facing interface.
- Use **QLoRA** (NF4 + double quant) for memory efficiency and accessibility.
- Prefer **DPO** as the first preference method (most mature); experiment with ORPO later.
- Adapters should be composable and loadable at inference time alongside the base model + system prompt.

---

## 2. Recommended First Traits

| Trait | Positive Direction | Negative Direction |
|-------|--------------------|--------------------|
| Warmth | Empathetic, supportive, human | Cold, purely transactional |
| Technical Precision | Exact, structured, detailed | Vague, hand-wavy |
| Conciseness | Clear and brief | Overly verbose |

---

## 3. Step-by-Step Training Pipeline

### Stage 0 — Preparation
1. Define clear behavioural rubrics for each trait.
2. Create or collect prompt sets.
3. Generate or curate **chosen vs rejected** response pairs that clearly demonstrate the trait difference.

### Stage 1 — Base Model
- Start from the current TRANC3 model (or a strong small open model for experiments).
- Ensure it is loadable under QLoRA (4-bit NF4).

### Stage 2 — QLoRA Configuration
- Bits: 4-bit NF4
- Double quantization: enabled
- LoRA rank: start with 8–16 for small models, up to 32–64 if needed
- Target modules: attention + MLP projections (standard)

### Stage 3 — Training
1. **SFT (Supervised Fine-Tuning)** on strong positive examples of the trait.
2. **DPO** (or ORPO) using the preference pairs.

### Stage 4 — Evaluation
- Automated trait-strength scoring (LLM-as-judge or simple heuristics).
- Side-by-side human review.
- Capability regression checks on core tasks.

### Stage 5 — Integration
- Save adapters under `src/personality/adapters/<trait_name>/`.
- Map existing JSON profiles to combinations of adapters.
- At inference:
  1. Load base model (optionally quantized).
  2. Load and merge/mix the selected trait adapters.
  3. Apply the original system prompt + sampling parameters from the JSON profile.

### Stage 6 — Iteration
- Agents can later propose refined profiles or request new adapters via the reflection loop.

---

## 4. Directory Layout Suggestion

```
src/personality/
├── profiles/               # existing JSON profiles
├── adapters/
│   ├── warmth/
│   ├── technical_precision/
│   └── conciseness/
├── loader.py               # loads & mixes adapters
└── training/
    ├── prepare_data.py
    ├── train_qlora_sft.py
    ├── train_dpo.py
    └── evaluate.py
```

---

## 5. ORPO vs DPO (Quick Reference)

| Aspect | DPO | ORPO |
|--------|-----|------|
| Stages | Usually SFT then DPO | Often single stage |
| Maturity | Very high | Growing |
| Simplicity | Excellent | Slightly simpler pipeline |
| Recommendation for v0.9.0 | **Start here** | Experiment later |
