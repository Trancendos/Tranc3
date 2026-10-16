"""
Personality Trait Adapters (QLoRA / LoRA)
========================================

This package holds trainable trait adapters that can be mixed at inference time
and mapped from the existing JSON personality profiles.

Design principles (v0.9.0):
- Keep the current JSON profiles in src/personality/profiles/ as the primary
  user-facing interface.
- Adapters are an optional stronger behavioural layer behind those profiles.
- Training uses QLoRA (NF4) + DPO (or ORPO) as documented in
  docs/architecture/PERSONALITY_ADAPTERS.md.

No adapters are trained yet; this is scaffolding only.
"""

from .loader import AdapterLoader, AdapterSpec

__all__ = ["AdapterLoader", "AdapterSpec"]
