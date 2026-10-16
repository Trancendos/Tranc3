# Personality Trait Adapters

Scaffolding for QLoRA / LoRA trait adapters (v0.9.0).

## Intent

- Existing JSON profiles in `../profiles/` remain the **primary** user interface.
- Adapters provide a stronger, composable behavioural layer behind those profiles.
- Training pipeline is documented in `docs/architecture/PERSONALITY_ADAPTERS.md`.

## Layout (planned)

```
adapters/
├── warmth/
├── technical_precision/
├── conciseness/
├── loader.py          # already present
└── training/          # scripts will live here later
```

## Current status

- Loader stub exists and is safe to import.
- No trained weights yet.
- No change to runtime behaviour until adapters are trained and the loader is wired into the inference path.
