"""The Trancendos taxonomy: Locations, AIs, Dimensionals.

The owner set this shape on 2026-09-11:

    Trancendos
      Locations
        <Location>            e.g. Infinity
          Abilities           (functions and features)
          Components
            Modules
              Nano-services
          Job Descriptions
          Power Ups
    AIs
      Tier 1 (Orchestrator)
        <AI>                  e.g. Cornelius MacIntyre
          Profile
            Personality
          Abilities
          Agents
          Bots
      Tier 2 (Primes) / Tier 3 (Lead AI)
    Dimensionals (Shared-Core)
      Services / Middleware / Databases / Mesh / Routers

Nothing here is a new register. Every level already had a source of truth
somewhere in this repo -- they were simply never assembled into one shape, so
the taxonomy existed as an idea and the filesystem existed as an accident, and
nothing could tell you where the two disagreed.

  Locations                <- PLATFORM_ENTITIES (43)
  Abilities                <- LocationEntity.abilities + primary_function
  Components/Modules/Nanos <- worker_path contents and src/nanoservices/
  Job Descriptions         <- JOB_DESCRIPTIONS + role seats (src/roles/registry.py)
  Power Ups                <- SHARD_CATALOGUE (workers/infinity-shards-service)
  AIs by tier              <- get_orchestration_tier()
  Profile / Personality    <- src/personality/profiles/*.json
  Agents / Bots            <- LocationEntity.agent_alpha/beta, agent_teams, bot_01..04
  Dimensionals             <- Dimensionals/ subpackages, src/mesh/, router modules

This package therefore *derives* the tree and reports where a level has no
source, rather than inviting anyone to type the answer in. A gap here is a real
gap in the platform, and `scripts/build_taxonomy_tree.py --check` keeps the
published tree equal to the measured one.
"""

from src.taxonomy.build import build_tree, gaps
from src.taxonomy.model import Node, Tree

__all__ = ["Node", "Tree", "build_tree", "gaps"]
