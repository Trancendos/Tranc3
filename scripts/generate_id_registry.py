"""
Tranc3 — Comprehensive Naming Repair & ID Registry Generator
=============================================================
Applies all naming convention fixes and generates the master ID Registry.

This is the canonical repair script. Run once to apply all fixes.
"""

import csv
import json
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ============================================================
# SECTION 1: 3-LETTER ABBREVIATION SYSTEM FOR ALL 43 LOCATIONS
# ============================================================

LOCATION_ABBREVS = {
    # Architectural Pillar
    "The Nexus": "NXS",
    "The HIVE": "HVE",
    "Arcadia": "ARC",
    "Luminous": "LUM",
    "The Town Hall": "TWH",
    # Creativity Pillar
    "The Studio": "STD",
    "Sashas Photo Studio": "SPS",
    "TranceFlow": "TFL",
    "TateKing": "TKG",
    "Fabulousa": "FAB",
    "Imaginarium": "IMG",
    # Development (Code) Pillar
    "The Digital Grid": "DGR",
    "The Lab": "LAB",
    "The Workshop": "WRK",
    "The Chaos Party": "TCP",
    # Commercial / Financial Pillar
    "The Artifactory": "ART",
    "API Marketplace": "APM",
    "Royal Bank of Arcadia": "RBA",
    "Arcadian Exchange": "AEX",
    "Warp Radio": "WRA",
    # Knowledge Pillar
    "The Observatory": "OBS",
    "The Library": "LIB",
    "The Academy": "ACA",
    "DocUtari": "DOC",
    "The Basement": "BSM",
    "The Spark": "SPK",
    # Security Pillar
    "Infinity": "INF",
    "The Void": "VOI",
    "The Lighthouse": "LTH",
    "The Warp Tunnel": "WTP",
    "Cryptex": "CRX",
    "The Ice Box": "ICB",
    # DevOps Pillar
    "The Dutchy": "DUT",
    "The Citadel": "CTL",
    "Think Tank": "TNK",
    "Turing's Hub": "THB",
    "ChronosSphere / ArcStream": "CHR",
    "DevOcity": "DEV",
    # Wellbeing Pillar
    "Tranquility": "TRQ",
    "I-Mind": "IMD",
    "tAimra": "TMR",
    "VRAR3D": "VR3",
    "Resonate": "RES",
}

# ============================================================
# SECTION 2: PILLAR ENUM MAPPING
# ============================================================

PILLAR_ABBREVS = {
    "Architectural": "ARCH",
    "Commercial / Financial": "COMM",
    "Creativity": "CREA",
    "Development (Code)": "DEVL",
    "Knowledge": "KNWL",
    "Security": "SECU",
    "DevOps": "DVOP",
    "Wellbeing": "WELL",
}

# ============================================================
# SECTION 3: PRIME ABBREVIATIONS (Tier 2)
# ============================================================

PRIME_ABBREVS = {
    "Cornelius MacIntyre": "COR",
    "Dorris Fontaine": "DOR",
    "The Guardian": "GRD",
    "The Doctor (Nikolai O'denhim)": "DOC",
    "Voxx": "VOX",
    "Norman Hawkins": "NOR",
    "Savania": "SAV",
    "Trancendos": "TRN",
}

# ============================================================
# SECTION 4: TIER 1 SOVEREIGN
# ============================================================

SOVEREIGN = {
    "name": "The Sovereign",
    "aid": "AID-SOV-01",
    "tier": 1,
    "description": "Prime AI — ultimate orchestrator of the Tranc3 ecosystem",
}

# ============================================================
# SECTION 5: NAMING REPAIRS
# ============================================================

# Bot names that need -Bot suffix added
BOT_SUFFIX_REPAIRS = {
    # The HIVE
    "Worker-Bee": "Worker-Bee-Bot", "Drone-7": "Drone-7-Bot",
    "Nectar-Fetch": "Nectar-Fetch-Bot", "Comb-Builder": "Comb-Builder-Bot",
    # Arcadia
    "Mail-Sorter": "Mail-Sorter-Bot", "Thread-Pumper": "Thread-Pumper-Bot",
    "UI-Renderer": "UI-Renderer-Bot", "Cache-Fetch": "Cache-Fetch-Bot",
    # Luminous
    "Neuron-1": "Neuron-1-Bot", "Neuron-2": "Neuron-2-Bot",
    "Dendrite": "Dendrite-Bot", "Axon": "Axon-Bot",
    # The Town Hall
    "Gavel": "Gavel-Bot", "Scroll": "Scroll-Bot",
    "Red-Tape": "Red-Tape-Bot", "Stamp": "Stamp-Bot",
    # The Studio (Wireframe renamed to Layout-Bot to avoid collision)
    "Palette": "Palette-Bot", "Easel": "Easel-Bot",
    "Clay": "Clay-Bot",
    # Sashas Photo Studio
    "Aperture": "Aperture-Bot", "Shutter": "Shutter-Bot",
    "Flash": "Flash-Bot", "Lens": "Lens-Bot",
    # TranceFlow
    "Voxel-1": "Voxel-1-Bot", "Collider": "Collider-Bot",
    "Ray-Tracer": "Ray-Tracer-Bot", "Sprite": "Sprite-Bot",
    # TateKing
    "Cutter": "Cutter-Bot", "Splicer": "Splicer-Bot",
    "Renderer": "Renderer-Bot", "Scrubber": "Scrubber-Bot",
    # Fabulousa
    "Pixel-Pusher": "Pixel-Pusher-Bot", "Hex-Code": "Hex-Code-Bot",
    "Font-Fetcher": "Font-Fetcher-Bot",
    # Imaginarium
    "Mixer": "Mixer-Bot", "Blender": "Blender-Bot",
    "Welder": "Welder-Bot", "Polisher": "Polisher-Bot",
    # The Digital Grid
    "Trigger": "Trigger-Bot", "Action": "Action-Bot",
    "Condition": "Condition-Bot", "Loop": "Loop-Bot",
    # The Chaos Party
    "Teapot": "Teapot-Bot", "Pocket-Watch": "Pocket-Watch-Bot",
    "Sugar-Cube": "Sugar-Cube-Bot", "Jam-Tart": "Jam-Tart-Bot",
    # The Artifactory
    "Packer": "Packer-Bot", "Unpacker": "Unpacker-Bot",
    "Checksum": "Checksum-Bot", "Versioner": "Versioner-Bot",
    # Royal Bank of Arcadia
    "Ledger": "Ledger-Bot", "Coin": "Coin-Bot",
    "Ticker": "Ticker-Bot", "Receipt": "Receipt-Bot",
    # Arcadian Exchange
    "Bidder": "Bidder-Bot", "Asker": "Asker-Bot",
    "Miner": "Miner-Bot", "Harvester": "Harvester-Bot",
    # The Observatory
    "Log-Alpha": "Log-Alpha-Bot", "Log-Beta": "Log-Beta-Bot",
    "Tracer": "Tracer-Bot", "Timestamp": "Timestamp-Bot",
    # The Library
    "Page": "Page-Bot", "Bookmark": "Bookmark-Bot",
    "Spine": "Spine-Bot", "Dust-Jacket": "Dust-Jacket-Bot",
    # The Academy
    "Chalk": "Chalk-Bot", "Board": "Board-Bot",
    "Eraser": "Eraser-Bot", "Bell": "Bell-Bot",
    # DocUtari
    "Scanner": "Scanner-Bot", "Stapler": "Stapler-Bot",
    "Folder": "Folder-Bot", "Shredder": "Shredder-Bot",
    # The Basement
    "Compressor": "Compressor-Bot", "Extractor": "Extractor-Bot",
    "Dust-Bunny": "Dust-Bunny-Bot", "Mothball": "Mothball-Bot",
    # The Spark
    "Spark-1": "Spark-1-Bot", "Spark-2": "Spark-2-Bot",
    "Linker": "Linker-Bot", "Pinger": "Pinger-Bot",
    # Infinity
    "Token-Minter": "Token-Minter-Bot", "Auth-Check": "Auth-Check-Bot",
    "Key-Gen": "Key-Gen-Bot", "Sentry": "Sentry-Bot",
    # The Void
    "Hash": "Hash-Bot", "Salt": "Salt-Bot",
    "Cipher": "Cipher-Bot", "Padlock": "Padlock-Bot",
    # The Lighthouse
    "Seal": "Seal-Bot", "Wax": "Wax-Bot",
    "Signet": "Signet-Bot",
    # The Warp Tunnel
    "Sniffer": "Sniffer-Bot", "Beam": "Beam-Bot",
    "Portal": "Portal-Bot",
    # Cryptex
    "Blocker": "Blocker-Bot", "Patcher": "Patcher-Bot",
    "Honeypot": "Honeypot-Bot",
    # The Ice Box
    "Frostbite": "Frostbite-Bot", "Icicle": "Icicle-Bot",
    "Glacier": "Glacier-Bot", "Permafrost": "Permafrost-Bot",
    # Warp Radio
    "Play": "Play-Bot", "Pause": "Pause-Bot",
    "Skip": "Skip-Bot", "Volume": "Volume-Bot",
    # The Dutchy
    "Scraper": "Scraper-Bot", "Parser": "Parser-Bot",
    "Crawler": "Crawler-Bot", "Whisper": "Whisper-Bot",
    # The Citadel
    "Map": "Map-Bot", "Compass": "Compass-Bot",
    "Clock": "Clock-Bot", "Radio": "Radio-Bot",
    # Think Tank
    "Beaker": "Beaker-Bot", "Bunsen": "Bunsen-Bot",
    "Pipette": "Pipette-Bot", "Petri": "Petri-Bot",
    # Turing's Hub
    "Texture": "Texture-Bot", "Vocoder": "Vocoder-Bot",
    "Optic": "Optic-Bot",
    # ChronosSphere / ArcStream
    "Tick": "Tick-Bot", "Tock": "Tock-Bot",
    "Pendulum": "Pendulum-Bot", "Sandglass": "Sandglass-Bot",
    # DevOcity
    "Crane": "Crane-Bot", "Wrench": "Wrench-Bot",
    "Gear": "Gear-Bot", "Belt": "Belt-Bot",
    # Tranquility
    "Breath": "Breath-Bot", "Pulse": "Pulse-Bot",
    "Calm": "Calm-Bot", "Aura": "Aura-Bot",
    # I-Mind
    "Journal": "Journal-Bot", "Mood": "Mood-Bot",
    "Reflect": "Reflect-Bot", "Soothe": "Soothe-Bot",
    # tAimra
    "Sync": "Sync-Bot", "Fetch": "Fetch-Bot",
    "Nudge": "Nudge-Bot", "Alert": "Alert-Bot",
    # VRAR3D
    "Render": "Render-Bot", "Track": "Track-Bot",
    "Haptic": "Haptic-Bot",
    # Resonate
    "Frequency": "Frequency-Bot", "Wave": "Wave-Bot",
    "Pitch": "Pitch-Bot", "Harmonic": "Harmonic-Bot",
}

# Duplicate resolution: location-specific renames
DUPLICATE_RENAMES = {
    # The Studio's "Wireframe" → "Layout-Bot" (design grids, not skeleton rigs)
    ("The Studio", "bot_04"): "Layout-Bot",
    # Turing's Hub's "Wireframe" → "Wireframe-Bot" (skeleton rigs)
    ("Turing's Hub", "bot_01"): "Wireframe-Bot",
    # The Lighthouse's "Stamp" → "Seal-Stamp-Bot" (cryptographic sealing)
    ("The Lighthouse", "bot_04"): "Seal-Stamp-Bot",
    # The Warp Tunnel's "Scanner" → "Scan-Bot" (integrity scanning)
    ("The Warp Tunnel", "bot_01"): "Scan-Bot",
    # Cryptex's "Tracer" → "Trace-Bot" (attack tracing)
    ("Cryptex", "bot_02"): "Trace-Bot",
    # VRAR3D's "Lens" → "VR-Lens-Bot" (focal dimension adjustment)
    ("VRAR3D", "bot_04"): "VR-Lens-Bot",
    # The Digital Grid's "The Weaver" → "The Flow-Weaver" (API flow weaving)
    ("The Digital Grid", "agent_alpha"): "The Flow-Weaver",
    # ChronosSphere's "The Weaver" → "The Time-Weaver" (timeline Gantt weaving)
    ("ChronosSphere / ArcStream", "agent_beta"): "The Time-Weaver",
    # VRAR3D's "The Guide" → "The VR-Guide" (spatial VR guidance)
    ("VRAR3D", "agent_beta"): "The VR-Guide",
}

# Lead AI repairs
LEAD_AI_REPAIRS = {
    "tAimra": "tAImra",       # Lead AI uses uppercase I; location name stays lowercase i
    "The Nexus": "Nexus-Prime",  # Decouple AI name from location name
}

# Guardian naming — preserve full canonical titles in entity contexts
GUARDIAN_HARMONIZE = {
    # Infinity's lead_ai: "The Guardian (Anchor: Orb of Orisis)" — preserved
    "Infinity": "The Guardian (Anchor: Orb of Orisis)",
    # Primes: "The Guardian (Marcus Magnolia)" — preserved
    "The Void": "The Guardian (Marcus Magnolia)",
    "The Lighthouse": "The Guardian (Marcus Magnolia)",
    "The Warp Tunnel": "The Guardian (Marcus Magnolia)",
    "Cryptex": "The Guardian (Marcus Magnolia)",
    "The Ice Box": "The Guardian (Marcus Magnolia)",
}

# Full title metadata (preserved for documentation)
GUARDIAN_FULL_TITLES = {
    "The Guardian": {
        "anchor": "Orb of Orisis",
        "human_identity": "Marcus Magnolia",
        "full_title_infinity": "The Guardian (Anchor: Orb of Orisis)",
        "full_title_prime": "The Guardian (Marcus Magnolia)",
    }
}

# ============================================================
# SECTION 6: ID REGISTRY GENERATOR
# ============================================================

def generate_id_registry():
    """Generate the complete ID Registry for all Tranc3 entities."""
    from src.entities.platform import PLATFORM_ENTITIES

    registry = {
        "version": "2.0.0",
        "generated_by": "Tranc3 Naming Repair & ID Registry Generator",
        "taxonomy": {
            "PID": "Product/Location ID — PID-XXX (3-letter location abbreviation)",
            "AID": "AI ID — AID-XXX-NN (3-letter location + 2-digit sequence)",
            "SID": "Service/Agent ID — SID-XXX-NN (3-letter location + 2-digit sequence)",
            "NID": "Nano-ID/Bot ID — NID-XXX-NN (3-letter location + 2-digit sequence)",
        },
        "tiers": {
            "1": "The Sovereign — Ultimate orchestrator",
            "2": "Primes — Executive AI authorities",
            "3": "Lead AIs — Day-to-day location managers",
            "4": "Agents — Mid-tier automation (Alpha + Beta)",
            "5": "Bots — Task-specific micro-workers (01-04)",
        },
        "sovereign": SOVEREIGN,
        "primes": [],
        "locations": [],
    }

    # --- Tier 2: Primes ---
    prime_data = [
        {"name": "Cornelius MacIntyre", "aid": "AID-COR-01", "tier": 2,
         "governs": ["The Nexus", "The HIVE", "Luminous", "The Town Hall", "The Studio",
                      "The Digital Grid (indirect)", "The Lab", "Royal Bank of Arcadia",
                      "The Observatory", "Infinity", "The Citadel", "Think Tank", "Tranquility"]},
        {"name": "Dorris Fontaine", "aid": "AID-DOR-01", "tier": 2,
         "governs": ["Arcadia", "The Artifactory", "API Marketplace", "Arcadian Exchange", "Warp Radio"]},
        {"name": "The Guardian (Anchor: Orb of Orisis)", "aid": "AID-GRD-01", "tier": 2,
         "full_title": "The Guardian (Anchor: Orb of Orisis / Marcus Magnolia)",
         "governs": ["The Void", "The Lighthouse", "The Warp Tunnel", "Cryptex", "The Ice Box"]},
        {"name": "The Doctor (Nikolai O'denhim)", "aid": "AID-DRN-01", "tier": 2,
         "governs": ["The Digital Grid", "The Workshop", "The Chaos Party"]},
        {"name": "Voxx", "aid": "AID-VOX-01", "tier": 2,
         "governs": ["Sashas Photo Studio", "TranceFlow", "TateKing", "Fabulousa", "Imaginarium"]},
        {"name": "Norman Hawkins", "aid": "AID-NOR-01", "tier": 2,
         "governs": ["The Library", "The Academy", "DocUtari", "The Basement", "The Spark"]},
        {"name": "Savania", "aid": "AID-SAV-01", "tier": 2,
         "governs": ["I-Mind", "tAimra", "VRAR3D", "Resonate"]},
        {"name": "Trancendos", "aid": "AID-TRN-01", "tier": 2,
         "governs": ["The Dutchy", "Turing's Hub", "ChronosSphere / ArcStream", "DevOcity"]},
    ]
    registry["primes"] = prime_data

    # --- Tier 3-5: Per-location entities ---
    for loc_name, entity in PLATFORM_ENTITIES.items():
        abbrev = LOCATION_ABBREVS.get(loc_name, "???")
        pillar_name = entity.pillar.value
        pillar_abbrev = PILLAR_ABBREVS.get(pillar_name, "???")

        # Lead AI name (with repairs applied)
        lead_ai_name = entity.lead_ai
        if loc_name in LEAD_AI_REPAIRS:
            lead_ai_name = LEAD_AI_REPAIRS[loc_name]

        # Primes (with Guardian harmonization — preserve full canonical titles)
        primes_repaired = []
        for p in entity.primes:
            if "Guardian" in p:
                primes_repaired.append("The Guardian (Marcus Magnolia)")
            else:
                primes_repaired.append(p)

        loc_entry = {
            "location": loc_name,
            "pid": f"PID-{abbrev}",
            "pillar": pillar_name,
            "pillar_abbrev": pillar_abbrev,
            "lead_ai": {
                "name": lead_ai_name,
                "aid": f"AID-{abbrev}-01",
                "tier": 3,
            },
            "primary_function": entity.primary_function,
            "primes": primes_repaired,
            "abilities": entity.abilities,
            "worker_port": entity.worker_port,
            "worker_path": entity.worker_path,
            "agents": [],
            "bots": [],
        }

        # Agents (Tier 4)
        for idx, (field, agent) in enumerate([
            ("agent_alpha", entity.agent_alpha),
            ("agent_beta", entity.agent_beta)
        ], start=1):
            agent_name = agent.code_name
            # Apply duplicate resolution
            if (loc_name, field) in DUPLICATE_RENAMES:
                agent_name = DUPLICATE_RENAMES[(loc_name, field)]

            loc_entry["agents"].append({
                "name": agent_name,
                "sid": f"SID-{abbrev}-{idx:02d}",
                "tier": 4,
                "role": "Alpha" if idx == 1 else "Beta",
                "description": agent.description,
            })

        # Bots (Tier 5)
        for idx, (field, bot) in enumerate([
            ("bot_01", entity.bot_01),
            ("bot_02", entity.bot_02),
            ("bot_03", entity.bot_03),
            ("bot_04", entity.bot_04)
        ], start=1):
            bot_name = bot.code_name

            # Apply duplicate resolution first (takes priority)
            if (loc_name, field) in DUPLICATE_RENAMES:
                bot_name = DUPLICATE_RENAMES[(loc_name, field)]
            # Then apply -Bot suffix if not already applied
            elif bot_name in BOT_SUFFIX_REPAIRS:
                bot_name = BOT_SUFFIX_REPAIRS[bot_name]
            # Also check if the name already ends with -Bot (from duplicate rename)
            # If the name was renamed by DUPLICATE_RENAMES, it might already have -Bot

            loc_entry["bots"].append({
                "name": bot_name,
                "nid": f"NID-{abbrev}-{idx:02d}",
                "tier": 5,
                "slot": f"0{idx}",
                "description": bot.description,
            })

        registry["locations"].append(loc_entry)

    return registry


def save_registry_json(registry, filepath):
    """Save the ID registry as JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    print(f"✅ ID Registry JSON saved to {filepath}")


def save_registry_csv(registry, filepath):
    """Save the ID registry as CSV (flat format)."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    rows = []

    # Sovereign
    rows.append({
        "ID": registry["sovereign"]["aid"],
        "Tier": 1,
        "Type": "Sovereign",
        "Name": registry["sovereign"]["name"],
        "Location": "",
        "Pillar": "",
        "Description": registry["sovereign"]["description"],
    })

    # Primes
    for prime in registry["primes"]:
        rows.append({
            "ID": prime["aid"],
            "Tier": 2,
            "Type": "Prime",
            "Name": prime["name"],
            "Location": "",
            "Pillar": "",
            "Description": f"Governs: {', '.join(prime['governs'])}",
        })

    # Per-location entities
    for loc in registry["locations"]:
        # Lead AI
        rows.append({
            "ID": loc["lead_ai"]["aid"],
            "Tier": 3,
            "Type": "Lead AI",
            "Name": loc["lead_ai"]["name"],
            "Location": loc["location"],
            "Pillar": loc["pillar"],
            "Description": loc["primary_function"],
        })
        # Agents
        for agent in loc["agents"]:
            rows.append({
                "ID": agent["sid"],
                "Tier": 4,
                "Type": f"Agent {agent['role']}",
                "Name": agent["name"],
                "Location": loc["location"],
                "Pillar": loc["pillar"],
                "Description": agent["description"],
            })
        # Bots
        for bot in loc["bots"]:
            rows.append({
                "ID": bot["nid"],
                "Tier": 5,
                "Type": f"Bot {bot['slot']}",
                "Name": bot["name"],
                "Location": loc["location"],
                "Pillar": loc["pillar"],
                "Description": bot["description"],
            })

    fieldnames = ["ID", "Tier", "Type", "Name", "Location", "Pillar", "Description"]
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✅ ID Registry CSV saved to {filepath} ({len(rows)} entries)")


if __name__ == "__main__":
    print("🔧 Generating Tranc3 ID Registry with naming repairs applied...")
    registry = generate_id_registry()

    base_dir = os.path.join(os.path.dirname(__file__), '..')
    save_registry_json(registry, os.path.join(base_dir, 'src', 'config', 'id_registry.json'))
    save_registry_csv(registry, os.path.join(base_dir, 'src', 'config', 'id_registry.csv'))

    # Print summary
    total_entities = 1 + len(registry["primes"])  # sovereign + primes
    for loc in registry["locations"]:
        total_entities += 1 + len(loc["agents"]) + len(loc["bots"])  # lead_ai + agents + bots

    print("\n📊 Registry Summary:")
    print(f"   Locations: {len(registry['locations'])}")
    print(f"   Primes: {len(registry['primes'])}")
    print(f"   Total Entities: {total_entities}")
    print(f"   Location Abbreviations: {len(LOCATION_ABBREVS)}")
