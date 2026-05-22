"""
Tranc3 Naming Convention Repair Script
=======================================
Systematically fixes all naming inconsistencies across the platform entity hierarchy.

Repairs:
1. tAImra → tAimra (Lead AI field casing to match location name)
2. Bot -Bot suffix: Standardize all bot names to Title-Case-Bot format
3. Duplicate name resolution with contextual suffixes
4. The Nexus AI decoupling from location name
5. Guardian dual naming: Harmonize but preserve anchor distinctions
6. Duplicate bots: Scanner, Stamp, Tracer, Lens
7. Duplicate agents: The Weaver (3x), The Guide (2x)
"""

# ============================================================
# REPAIR MAP: Bot names that need -Bot suffix
# ============================================================
# Rule: All Tier 5 bots must end with -Bot (Title-Case-Bot format)
# Some already have it (Ping-Bot, Ack-Bot, Lint-Bot, etc.)
# Many don't: Gavel, Scroll, Hash, Salt, etc.

BOT_SUFFIX_REPAIRS = {
    # The HIVE — already hyphenated but missing -Bot
    "Worker-Bee": "Worker-Bee-Bot",  # or just Worker-Bot? Keep the bee theme
    "Drone-7": "Drone-7-Bot",
    "Nectar-Fetch": "Nectar-Fetch-Bot",
    "Comb-Builder": "Comb-Builder-Bot",
    
    # Arcadia
    "Mail-Sorter": "Mail-Sorter-Bot",
    "Thread-Pumper": "Thread-Pumper-Bot",
    "UI-Renderer": "UI-Renderer-Bot",
    "Cache-Fetch": "Cache-Fetch-Bot",
    
    # Luminous
    "Neuron-1": "Neuron-1-Bot",
    "Neuron-2": "Neuron-2-Bot",
    "Dendrite": "Dendrite-Bot",
    "Axon": "Axon-Bot",
    
    # The Town Hall
    "Gavel": "Gavel-Bot",
    "Scroll": "Scroll-Bot",
    "Red-Tape": "Red-Tape-Bot",
    "Stamp": "Stamp-Bot",  # NOTE: also in The Lighthouse — resolved with context suffix below
    
    # The Studio
    "Palette": "Palette-Bot",
    "Easel": "Easel-Bot",
    "Clay": "Clay-Bot",
    "Wireframe": "Wireframe-Bot",  # Studio context
    
    # Sashas Photo Studio
    "Aperture": "Aperture-Bot",
    "Shutter": "Shutter-Bot",
    "Flash": "Flash-Bot",
    "Lens": "Lens-Bot",  # Photo Studio context
    
    # TranceFlow
    "Voxel-1": "Voxel-1-Bot",
    "Collider": "Collider-Bot",
    "Ray-Tracer": "Ray-Tracer-Bot",
    "Sprite": "Sprite-Bot",
    
    # TateKing
    "Cutter": "Cutter-Bot",
    "Splicer": "Splicer-Bot",
    "Renderer": "Renderer-Bot",
    "Scrubber": "Scrubber-Bot",
    
    # Fabulousa
    "Pixel-Pusher": "Pixel-Pusher-Bot",
    "Hex-Code": "Hex-Code-Bot",
    "Font-Fetcher": "Font-Fetcher-Bot",
    # Padding-Bot already has suffix ✓
    
    # Imaginarium
    "Mixer": "Mixer-Bot",
    "Blender": "Blender-Bot",
    "Welder": "Welder-Bot",
    "Polisher": "Polisher-Bot",
    
    # The Digital Grid
    "Trigger": "Trigger-Bot",
    "Action": "Action-Bot",
    "Condition": "Condition-Bot",
    "Loop": "Loop-Bot",
    
    # The Chaos Party
    "Teapot": "Teapot-Bot",
    "Pocket-Watch": "Pocket-Watch-Bot",
    "Sugar-Cube": "Sugar-Cube-Bot",
    "Jam-Tart": "Jam-Tart-Bot",
    
    # The Artifactory
    "Packer": "Packer-Bot",
    "Unpacker": "Unpacker-Bot",
    "Checksum": "Checksum-Bot",
    "Versioner": "Versioner-Bot",
    
    # Royal Bank of Arcadia
    "Ledger": "Ledger-Bot",
    "Coin": "Coin-Bot",
    "Ticker": "Ticker-Bot",
    "Receipt": "Receipt-Bot",
    
    # Arcadian Exchange
    "Bidder": "Bidder-Bot",
    "Asker": "Asker-Bot",
    "Miner": "Miner-Bot",
    "Harvester": "Harvester-Bot",
    
    # The Observatory
    "Log-Alpha": "Log-Alpha-Bot",
    "Log-Beta": "Log-Beta-Bot",
    "Tracer": "Tracer-Bot",  # Observatory context
    "Timestamp": "Timestamp-Bot",
    
    # The Library
    "Page": "Page-Bot",
    "Bookmark": "Bookmark-Bot",
    "Spine": "Spine-Bot",
    "Dust-Jacket": "Dust-Jacket-Bot",
    
    # The Academy
    "Chalk": "Chalk-Bot",
    "Board": "Board-Bot",
    "Eraser": "Eraser-Bot",
    "Bell": "Bell-Bot",
    
    # DocUtari
    "Scanner": "Scanner-Bot",  # DocUtari context
    "Stapler": "Stapler-Bot",
    "Folder": "Folder-Bot",
    "Shredder": "Shredder-Bot",
    
    # The Basement
    "Compressor": "Compressor-Bot",
    "Extractor": "Extractor-Bot",
    "Dust-Bunny": "Dust-Bunny-Bot",
    "Mothball": "Mothball-Bot",
    
    # The Spark
    "Spark-1": "Spark-1-Bot",
    "Spark-2": "Spark-2-Bot",
    "Linker": "Linker-Bot",
    "Pinger": "Pinger-Bot",
    
    # Infinity
    "Token-Minter": "Token-Minter-Bot",
    "Auth-Check": "Auth-Check-Bot",
    "Key-Gen": "Key-Gen-Bot",
    "Sentry": "Sentry-Bot",
    
    # The Void
    "Hash": "Hash-Bot",
    "Salt": "Salt-Bot",
    "Cipher": "Cipher-Bot",
    "Padlock": "Padlock-Bot",
    
    # The Lighthouse
    "Seal": "Seal-Bot",
    "Wax": "Wax-Bot",
    "Signet": "Signet-Bot",
    # Stamp in Lighthouse — contextual duplicate resolved below
    
    # The Warp Tunnel
    # Scanner in Warp Tunnel — contextual duplicate resolved below
    "Sniffer": "Sniffer-Bot",
    "Beam": "Beam-Bot",
    "Portal": "Portal-Bot",
    
    # Cryptex
    "Blocker": "Blocker-Bot",
    # Tracer in Cryptex — contextual duplicate resolved below
    "Patcher": "Patcher-Bot",
    "Honeypot": "Honeypot-Bot",
    
    # The Ice Box
    "Frostbite": "Frostbite-Bot",
    "Icicle": "Icicle-Bot",
    "Glacier": "Glacier-Bot",
    "Permafrost": "Permafrost-Bot",
    
    # Warp Radio
    "Play": "Play-Bot",
    "Pause": "Pause-Bot",
    "Skip": "Skip-Bot",
    "Volume": "Volume-Bot",
    
    # The Dutchy
    "Scraper": "Scraper-Bot",
    "Parser": "Parser-Bot",
    "Crawler": "Crawler-Bot",
    "Whisper": "Whisper-Bot",
    
    # The Citadel
    "Map": "Map-Bot",
    "Compass": "Compass-Bot",
    "Clock": "Clock-Bot",
    "Radio": "Radio-Bot",
    
    # Think Tank
    "Beaker": "Beaker-Bot",
    "Bunsen": "Bunsen-Bot",
    "Pipette": "Pipette-Bot",
    "Petri": "Petri-Bot",
    
    # Turing's Hub
    # Wireframe in Turing's Hub — contextual duplicate resolved below
    "Texture": "Texture-Bot",
    "Vocoder": "Vocoder-Bot",
    "Optic": "Optic-Bot",
    
    # ChronosSphere / ArcStream
    "Tick": "Tick-Bot",
    "Tock": "Tock-Bot",
    "Pendulum": "Pendulum-Bot",
    "Sandglass": "Sandglass-Bot",
    
    # DevOcity
    "Crane": "Crane-Bot",
    "Wrench": "Wrench-Bot",
    "Gear": "Gear-Bot",
    "Belt": "Belt-Bot",
    
    # Tranquility
    "Breath": "Breath-Bot",
    "Pulse": "Pulse-Bot",
    "Calm": "Calm-Bot",
    "Aura": "Aura-Bot",
    
    # I-Mind
    "Journal": "Journal-Bot",
    "Mood": "Mood-Bot",
    "Reflect": "Reflect-Bot",
    "Soothe": "Soothe-Bot",
    
    # tAimra
    "Sync": "Sync-Bot",
    "Fetch": "Fetch-Bot",
    "Nudge": "Nudge-Bot",
    "Alert": "Alert-Bot",
    
    # VRAR3D
    "Render": "Render-Bot",
    "Track": "Track-Bot",
    "Haptic": "Haptic-Bot",
    # Lens in VRAR3D — contextual duplicate resolved below
    
    # Resonate
    "Frequency": "Frequency-Bot",
    "Wave": "Wave-Bot",
    "Pitch": "Pitch-Bot",
    "Harmonic": "Harmonic-Bot",
}

# ============================================================
# DUPLICATE NAME RESOLUTION (with contextual suffixes)
# ============================================================

DUPLICATE_RESOLUTIONS = {
    # Bots
    "The Lighthouse/Stamp": "Stamp-Bot",          # Lighthouse stamps cryptographic seals
    "The Town Hall/Stamp": "Stamp-Bot",            # Town Hall stamps certificates (same name OK with -Bot suffix + different PID context)
    # Since IDs will disambiguate, we keep the descriptive name but add context in description
    # However, for absolute clarity in the code_name field, we add a context qualifier:
    "The Lighthouse/bot_04": "Seal-Stamp-Bot",     # Cryptographic seal stamping
    # Town Hall's Stamp becomes Stamp-Bot (certificate stamping) — already in BOT_SUFFIX_REPAIRS
    
    "The Warp Tunnel/bot_01": "Scan-Bot",          # Warp Tunnel scans for integrity; different from DocUtari's Scanner
    "DocUtari/bot_01": "Scanner-Bot",              # DocUtari scans documents (OCR)
    
    "Cryptex/bot_02": "Trace-Bot",                 # Cryptex traces attack origins
    "The Observatory/bot_03": "Tracer-Bot",        # Observatory traces data paths
    
    "VRAR3D/bot_04": "VR-Lens-Bot",                # VRAR3D focal lens adjustment
    "Sashas Photo Studio/bot_04": "Lens-Bot",      # Photo lens correction
    
    # Turing's Hub Wireframe vs The Studio Wireframe
    "Turing's Hub/bot_01": "Wireframe-Bot",        # Builds skeleton rigs
    "The Studio/bot_04": "Layout-Bot",             # Plots design grids (renamed to avoid collision)
    
    # Agents
    "The Digital Grid/agent_alpha": "The Flow-Weaver",     # Weaves APIs into execution flows
    "ChronosSphere / ArcStream/agent_beta": "The Time-Weaver",  # Weaves timeline Gantt views
    "Fabulousa/agent_beta": "The Weaver",                   # Weaves mockups into code — original name kept (first usage)
    
    "Tranquility/agent_alpha": "The Guide",                  # Guides to wellbeing sub-nodes — original name kept
    "VRAR3D/agent_beta": "The VR-Guide",                     # Guides through VR spatial tasks
}

# ============================================================
# LEAD AI REPAIRS
# ============================================================

LEAD_AI_REPAIRS = {
    # tAImra casing: Location is "tAimra", Lead AI should be "tAimra" (matching)
    # The distinction is intentional (location vs AI entity) but casing should be consistent
    "tAimra": "tAimra",  # Change lead_ai from "tAImra" to "tAimra"
    
    # The Nexus: Lead AI is currently "The Nexus" (same as location) — decouple
    "The Nexus": "Nexus-Prime",  # New Lead AI name, distinct from location
}

# ============================================================
# GUARDIAN NAMING HARMONIZATION
# ============================================================
# The Guardian has two forms:
# - "The Guardian (Anchor: Orb of Orisis)" — Infinity's Lead AI
# - "The Guardian (Marcus Magnolia)" — Prime for The Void, Lighthouse, Warp Tunnel, Cryptex, Ice Box
# These are actually the SAME entity (The Guardian) with different context qualifiers.
# The Anchor (Orb of Orisis) is a power/artifact the Guardian wields.
# Marcus Magnolia is the Guardian's human identity/name.
# Resolution: Keep both qualifiers as they serve different purposes:
# - As Lead AI: "The Guardian" (without qualifier — the qualifier is about their power, not identity)
# - As Prime: "The Guardian" (without qualifier — Marcus Magnolia is internal lore)
# The full title should be documented but not clutter the entity name field.
# Add a `title` or `full_title` field if needed, but for now just harmonize the display name.

GUARDIAN_REPAIR = {
    "infinity_lead_ai": "The Guardian",  # Simplified from "The Guardian (Anchor: Orb of Orisis)"
    "void_prime": "The Guardian",         # Simplified from "The Guardian (Marcus Magnolia)"
    # Full titles preserved in ID registry metadata
}

print("Naming repair plan loaded. Run apply_repairs.py to execute.")
