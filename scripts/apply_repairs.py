"""
Apply all naming repairs to src/entities/platform.py
This script reads the current file, applies all naming convention fixes, and writes it back.
"""

import os

PLATFORM_PY_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'entities', 'platform.py')

# ============================================================
# ALL NAMING REPAIRS AS (old_string, new_string) PAIRS
# ============================================================

# These are applied in order. Each old_string must be unique in the file.

REPAIRS = [
    # --- 1. tAImra casing fix: Lead AI must use "tAImra" (uppercase I), location stays "tAimra" ---
    ('lead_ai="tAimra"', 'lead_ai="tAImra"'),

    # --- 2. The Nexus Lead AI decoupling ---
    # The Nexus location has lead_ai="The Nexus" — decouple
    ('location="The Nexus",\n        pillar=Pillar.ARCHITECTURAL,\n        lead_ai="The Nexus",',
     'location="The Nexus",\n        pillar=Pillar.ARCHITECTURAL,\n        lead_ai="Nexus-Prime",'),

    # --- 3. Guardian: Full canonical titles are preserved in entity contexts ---
    # "The Guardian (Anchor: Orb of Orisis)" for Infinity lead_ai
    # "The Guardian (Marcus Magnolia)" for primes — kept as-is

    # --- 4. (merged into #3 above) ---

    # --- 5. The Studio: Wireframe → Layout-Bot (design grid plotting, not skeleton rigging) ---
    ('bot_04=Bot("Wireframe", "Plots design grids, focal alignments, and bounds.")',
     'bot_04=Bot("Layout-Bot", "Plots design grids, focal alignments, and bounds.")'),

    # --- 6. The Digital Grid: The Weaver → The Flow-Weaver (API flow weaving) ---
    ('agent_alpha=Agent("The Weaver", "Weaves APIs, webhooks, and scripts into execution steps.")',
     'agent_alpha=Agent("The Flow-Weaver", "Weaves APIs, webhooks, and scripts into execution steps.")'),

    # --- 7. ChronosSphere: The Weaver → The Time-Weaver (timeline Gantt weaving) ---
    ('agent_beta=Agent("The Weaver", "Translates timeline parameters into interactive visual Gantt views.")',
     'agent_beta=Agent("The Time-Weaver", "Translates timeline parameters into interactive visual Gantt views.")'),

    # --- 8. VRAR3D: The Guide → The VR-Guide (spatial VR guidance) ---
    ('agent_beta=Agent("The Guide", "Leads users through structured spatial tasks within virtual relaxation areas.")',
     'agent_beta=Agent("The VR-Guide", "Leads users through structured spatial tasks within virtual relaxation areas.")'),

    # --- 9. The Lighthouse: Stamp → Seal-Stamp-Bot (cryptographic seal stamping) ---
    ('bot_04=Bot("Stamp", "Applies file-system metadata to register the exact creation details.")',
     'bot_04=Bot("Seal-Stamp-Bot", "Applies file-system metadata to register the exact creation details.")'),

    # --- 10. The Warp Tunnel: Scanner → Scan-Bot (integrity scanning) ---
    ('bot_01=Bot("Scanner", "Performs background sweeps on directories, reading cryptographic stamps.")',
     'bot_01=Bot("Scan-Bot", "Performs background sweeps on directories, reading cryptographic stamps.")'),

    # --- 11. Cryptex: Tracer → Trace-Bot (attack tracing) ---
    ('bot_02=Bot("Tracer", "Traces malicious attacks back to origin networks for reporting.")',
     'bot_02=Bot("Trace-Bot", "Traces malicious attacks back to origin networks for reporting.")'),

    # --- 12. VRAR3D: Lens → VR-Lens-Bot (focal dimension adjustment) ---
    ('bot_04=Bot("Lens", "Adjusts focal dimensions, scaling imagery dynamically to reduce eye strain.")',
     'bot_04=Bot("VR-Lens-Bot", "Adjusts focal dimensions, scaling imagery dynamically to reduce eye strain.")'),

    # --- 13. Remove NOTE comment about tAImra (the fix is now applied) ---
    ('    # NOTE: Location name is "tAimra"; Lead AI entity name is "tAImra" (different capitalisation).\n    "tAimra"',
     '    "tAimra"'),
]

# ============================================================
# BOT -Bot SUFFIX REPAIRS
# ============================================================
# These are applied to bot code_names that don't have the -Bot suffix

BOT_REPAIRS = {
    # Format: "old_name": "new_name"
    # Already have -Bot: Ping-Bot, Ack-Bot, Syn-Bot, Fin-Bot, Lint-Bot, Compile-Bot, Debug-Bot, Test-Bot,
    #                     Commit-Bot, Push-Bot, Pull-Bot, Clone-Bot, GET-Bot, POST-Bot, PUT-Bot, DELETE-Bot,
    #                     Padding-Bot, Spark-1-Bot (already has -Bot? No, it's Spark-1), etc.

    # The HIVE
    "Worker-Bee": "Worker-Bee-Bot",
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
    "Stamp": "Stamp-Bot",

    # The Studio (Wireframe already renamed to Layout-Bot above)
    "Palette": "Palette-Bot",
    "Easel": "Easel-Bot",
    "Clay": "Clay-Bot",

    # Sashas Photo Studio
    "Aperture": "Aperture-Bot",
    "Shutter": "Shutter-Bot",
    "Flash": "Flash-Bot",
    "Lens": "Lens-Bot",

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
    "Tracer": "Tracer-Bot",
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

    # DocUtari (Scanner already renamed to Scanner-Bot... wait no, it was renamed to Scan-Bot in Warp Tunnel)
    # DocUtari's Scanner gets -Bot suffix
    "Scanner": "Scanner-Bot",
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

    # The Lighthouse (Stamp already renamed to Seal-Stamp-Bot)
    "Seal": "Seal-Bot",
    "Wax": "Wax-Bot",
    "Signet": "Signet-Bot",

    # The Warp Tunnel (Scanner already renamed to Scan-Bot)
    "Sniffer": "Sniffer-Bot",
    "Beam": "Beam-Bot",
    "Portal": "Portal-Bot",

    # Cryptex (Tracer already renamed to Trace-Bot)
    "Blocker": "Blocker-Bot",
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

    # Turing's Hub (Wireframe already handled above)
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

    # VRAR3D (Lens already renamed to VR-Lens-Bot)
    "Render": "Render-Bot",
    "Track": "Track-Bot",
    "Haptic": "Haptic-Bot",

    # Resonate
    "Frequency": "Frequency-Bot",
    "Wave": "Wave-Bot",
    "Pitch": "Pitch-Bot",
    "Harmonic": "Harmonic-Bot",
}


def apply_repairs():
    """Apply all naming repairs to platform.py."""
    with open(PLATFORM_PY_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Apply targeted repairs first
    for old, new in REPAIRS:
        if old in content:
            content = content.replace(old, new)
            print(f"  ✅ Applied: {old[:60]}... → {new[:60]}...")
        else:
            print(f"  ⚠️ NOT FOUND: {old[:80]}...")

    # Apply bot -Bot suffix repairs
    # We need to be careful to only replace Bot() code_name arguments
    for old_name, new_name in BOT_REPAIRS.items():
        # Replace within Bot() constructor only
        old_pattern = 'Bot("' + old_name + '", "'
        new_pattern = 'Bot("' + new_name + '", "'
        if old_pattern in content:
            content = content.replace(old_pattern, new_pattern)
            print(f"  ✅ Bot suffix: {old_name} → {new_name}")
        else:
            # Might already have -Bot or been handled by DUPLICATE_RENAMES
            pass

    if content != original:
        with open(PLATFORM_PY_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n✅ All repairs applied to {PLATFORM_PY_PATH}")
    else:
        print("\n⚠️ No changes made — all patterns may already be applied or not found")

    return content != original


if __name__ == "__main__":
    print("🔧 Applying naming repairs to platform.py...")
    changed = apply_repairs()
    if changed:
        print("✅ Done! Run verification to check results.")
    else:
        print("⚠️ No changes applied.")
