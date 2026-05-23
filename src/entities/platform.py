"""
Trancendos Platform Entity Hierarchy
=====================================
43 named locations, each with a Lead AI (Tier 3), Primes (Tier 2),
Agent Alpha + Beta (Tier 4), and Bots 01–04 (Tier 5).

Canonical source of truth for entity names, roles, and worker mappings.

Universal ID Taxonomy:
  PID-XXX  - Product / Location ID   (3-letter abbreviation)
  AID-XXX-NN - AI ID                 (location abbrev + 2-digit sequence)
  SID-XXX-NN - Service / Agent ID    (location abbrev + 2-digit sequence)
  NID-XXX-NN - Nano-ID / Bot ID      (location abbrev + 2-digit sequence)

Tier System:
  Tier 1 — The Sovereign (ultimate orchestrator)
  Tier 2 - Primes (executive AI authorities)
  Tier 3 - Lead AIs (day-to-day location managers)
  Tier 4 - Agents (mid-tier automation: Alpha + Beta)
  Tier 5 - Bots (task-specific micro-workers: 01-04)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class Pillar(str, Enum):
    ARCHITECTURAL = "Architectural"
    COMMERCIAL_FINANCIAL = "Commercial / Financial"
    CREATIVITY = "Creativity"
    DEVELOPMENT_CODE = "Development (Code)"
    KNOWLEDGE = "Knowledge"
    SECURITY = "Security"
    DEVOPS = "DevOps"
    WELLBEING = "Wellbeing"


@dataclass
class Bot:
    code_name: str
    description: str
    nid: str = ""  # NID-XXX-NN — set automatically by _assign_ids()


@dataclass
class Agent:
    code_name: str
    description: str
    sid: str = ""  # SID-XXX-NN — set automatically by _assign_ids()


@dataclass
class LocationEntity:
    location: str
    pillar: Pillar
    lead_ai: str
    abilities: List[str]
    primary_function: str
    primes: List[str]
    online_mode: str
    offline_mode: str
    agent_alpha: Agent
    agent_beta: Agent
    bot_01: Bot
    bot_02: Bot
    bot_03: Bot
    bot_04: Bot
    # Universal ID Taxonomy
    pid: str = ""  # PID-XXX — Product/Location ID
    aid: str = ""  # AID-XXX-01 — Lead AI ID
    # Self-hosted worker port (None if not yet deployed as a worker)
    worker_port: Optional[int] = None
    # Path in this repo to the worker or source module
    worker_path: Optional[str] = None

    def to_health_meta(self) -> Dict:
        """Return a dict suitable for embedding in a worker /health response."""
        return {
            "location": self.location,
            "pillar": self.pillar.value,
            "lead_ai": self.lead_ai,
            "primes": self.primes,
            "primary_function": self.primary_function,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Registry — 43 platform locations
# ─────────────────────────────────────────────────────────────────────────────

PLATFORM_ENTITIES: Dict[str, LocationEntity] = {
    "The Nexus": LocationEntity(
        location="The Nexus",
        pillar=Pillar.ARCHITECTURAL,
        lead_ai="Nexus-Prime",
        abilities=[
            "Omni-Channel Routing: Parses and directs intent.",
            "Worker Migration: Transfers entities between hubs.",
        ],
        primary_function="AI Communication Gateway & AI, Agent, and Bot / Worker Transfer Hub",
        primes=["Cornelius MacIntyre"],
        online_mode="Real-time chat interface; active entity transfer.",
        offline_mode="Cached chat logs; delayed routing (queued).",
        agent_alpha=Agent("Pathfinder", "Maps fast system data communication routes."),
        agent_beta=Agent("Omni-Router", "Routes user prompts to the correct AI/Bot."),
        bot_01=Bot("Ping-Bot", "Measures connection network latency."),
        bot_02=Bot("Ack-Bot", "Confirms data transitions and logs stamps."),
        bot_03=Bot("Syn-Bot", "Harmonizes offline caches with cloud data."),
        bot_04=Bot("Fin-Bot", "Closes data channels and flushes memory."),
        worker_port=8004,
        worker_path="workers/infinity-ws/",
    ),
    "The HIVE": LocationEntity(
        location="The HIVE",
        pillar=Pillar.ARCHITECTURAL,
        lead_ai="The Queen",
        abilities=[
            "Swarm Packet Optimization: Compresses/reroutes data.",
            "Self-Healing Topology: Bypasses failed nodes.",
        ],
        primary_function="Data Transport Hub",
        primes=["Cornelius MacIntyre"],
        online_mode="High-speed data flow; swarm logic routing.",
        offline_mode="P2P local syncing; offline data queuing.",
        agent_alpha=Agent("Swarm-Leader", "Manages massive data streams and loads."),
        agent_beta=Agent("Hive-Mind", "Uses telemetry to optimize the routing matrix."),
        bot_01=Bot("Worker-Bee-Bot", "Carries small payload updates between nodes."),
        bot_02=Bot("Drone-7-Bot", "Sweeps transport lanes to prune stuck packets."),
        bot_03=Bot("Nectar-Fetch-Bot", "Pulls system-state configuration updates."),
        bot_04=Bot("Comb-Builder-Bot", "Creates dynamic memory blocks for spikes."),
        worker_port=8022,
        worker_path="workers/queue-service/",
    ),
    "Arcadia": LocationEntity(
        location="Arcadia",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        lead_ai="Lilli SC",
        abilities=[
            "Dynamic Dashboard: Renders personalized frontend.",
            "Integrated Comms Matrix: Centralizes forums/emails.",
        ],
        primary_function="Post-Login User Frontend, Forum & Email Hub",
        primes=["Dorris Fontaine"],
        online_mode="Primary web portal; live forum/email management.",
        offline_mode="Read-only forums; drafted posts; local UI render.",
        agent_alpha=Agent("Forum-Mod", "Scans threads to flag policy issues/announcements."),
        agent_beta=Agent("Campaign-Mgr", "Drafts automated system emails/notifications."),
        bot_01=Bot("Mail-Sorter-Bot", "Categorizes and dispatches inbound emails."),
        bot_02=Bot("Thread-Pumper-Bot", "Injects live forum updates into the UI."),
        bot_03=Bot("UI-Renderer-Bot", "Translates local templates into responsive UI."),
        bot_04=Bot("Cache-Fetch-Bot", "Grabs local media/templates to speed up loads."),
        worker_port=None,
        worker_path="web/",
    ),
    "Luminous": LocationEntity(
        location="Luminous",
        pillar=Pillar.ARCHITECTURAL,
        lead_ai="Cornelius MacIntyre",
        abilities=[
            "Cognitive Synthesis: Autonomous optimization decisions.",
            "Workflow Instantiation: Translates intent to execution.",
        ],
        primary_function="Core Platform Brain & Orchestration Engine",
        primes=["Cornelius MacIntyre"],
        online_mode="Executive Dashboard; live platform coordination.",
        offline_mode="Limited dashboard; offline workflow drafting.",
        agent_alpha=Agent(
            "Synapse", "Monitors global activity; triggers alerts for offline nodes."
        ),
        agent_beta=Agent("Cortex", "Translates objectives into workflow blueprints."),
        bot_01=Bot("Neuron-1-Bot", "Listens for emergency signals for immediate attention."),
        bot_02=Bot("Neuron-2-Bot", "Holds transient conversational state metrics."),
        bot_03=Bot("Dendrite-Bot", "Collects performance metrics from peripheral nodes."),
        bot_04=Bot("Axon-Bot", "Transmits executive commands to Agents/Bots."),
        worker_port=8009,
        worker_path="workers/infinity-ai/",
    ),
    "The Town Hall": LocationEntity(
        location="The Town Hall",
        pillar=Pillar.ARCHITECTURAL,
        lead_ai="Tristuran",
        abilities=[
            "Automated Compliance: Scans against ITIL/Agile.",
            "War Room Protocol: Locks down affected systems.",
        ],
        primary_function="Governance & Compliance Center",
        primes=["Cornelius MacIntyre"],
        online_mode="Live policy enforcement; War Room collaboration.",
        offline_mode="Offline policy review; localized incident drafting.",
        agent_alpha=Agent("The Auditor", "Compares operations against ITIL/Agile frameworks."),
        agent_beta=Agent("The Bailiff", "Flags non-compliant accounts, placing holds."),
        bot_01=Bot("Gavel-Bot", "Halts operations in sandboxes for security violations."),
        bot_02=Bot("Scroll-Bot", "Writes unalterable logs of compliance actions."),
        bot_03=Bot("Red-Tape-Bot", "Auto-generates compliance paperwork and checklists."),
        bot_04=Bot("Stamp-Bot", "Signs certificates for approved system tools."),
        worker_port=None,
        worker_path="src/townhall/",
    ),
    "The Studio": LocationEntity(
        location="The Studio",
        pillar=Pillar.CREATIVITY,
        lead_ai="Voxx",
        abilities=[
            "Creative Node Sync: Nervous system for creative tools.",
            "Aesthetic Homogenization: Enforces design languages.",
        ],
        primary_function="Central Hub of the Creativity Center",
        primes=["Cornelius MacIntyre"],
        online_mode="Centralized production access; live collaboration.",
        offline_mode="Localized asset creation; offline design drafting.",
        agent_alpha=Agent("The Conductor", "Coordinates asset handoffs between 3D/Video/UI."),
        agent_beta=Agent("The Muse", "Generates baseline design schemes and mood boards."),
        bot_01=Bot("Palette-Bot", "Translates color variables into matching stylesheets."),
        bot_02=Bot("Easel-Bot", "Renders dynamic design drafts for live preview."),
        bot_03=Bot("Clay-Bot", "Speeds up simple vector and morphing operations."),
        bot_04=Bot("Layout-Bot", "Plots design grids, focal alignments, and bounds."),
        worker_port=None,
        worker_path="src/studio/",
    ),
    "Sashas Photo Studio": LocationEntity(
        location="Sashas Photo Studio",
        pillar=Pillar.CREATIVITY,
        lead_ai="Madam Krystal",
        abilities=[
            "Generative Synthesis: Creates high-fidelity images.",
            "Algorithmic Retouching: Enhances/upscales imagery.",
        ],
        primary_function="Photo & Image Generation Center",
        primes=["Voxx"],
        online_mode="Live AI image generation; collaborative photo editing.",
        offline_mode="Localized photo editing; queued prompt drafting.",
        agent_alpha=Agent("The Retoucher", "Directs neural filters to enhance/sharpen pictures."),
        agent_beta=Agent("Prompt-Smith", "Optimizes prompts into tags for generation engines."),
        bot_01=Bot("Aperture-Bot", "Adjusts focus matrices, blur, and depth of field."),
        bot_02=Bot("Shutter-Bot", "Triggers high-speed renders to output flat image layers."),
        bot_03=Bot("Flash-Bot", "Regulates light direction, balance, and HDR variables."),
        bot_04=Bot("Lens-Bot", "Fixes perspective distortions and lens anomalies."),
        worker_port=None,
        worker_path="src/studio/",
    ),
    "TranceFlow": LocationEntity(
        location="TranceFlow",
        pillar=Pillar.CREATIVITY,
        lead_ai="Junior Cesar",
        abilities=[
            "Browser-Native Engine: Runs game logic/physics.",
            "Real-time Sculpting: Shapes/textures 3D spaces.",
        ],
        primary_function="3D Modeling & Games Creation Studio",
        primes=["Voxx"],
        online_mode="Live collaborative game dev; cloud rendering.",
        offline_mode="Local 3D model editing; offline game logic drafting.",
        agent_alpha=Agent("Mesh-Weaver", "Synthesizes wireframes and converts data to meshes."),
        agent_beta=Agent("The Physicist", "Calculates rigid body dynamics and object collision."),
        bot_01=Bot("Voxel-1-Bot", "Generates grid-based blocks and terrain geometries."),
        bot_02=Bot("Collider-Bot", "Monitors boundary boxes for collision scripts."),
        bot_03=Bot("Ray-Tracer-Bot", "Handles lighting paths, reflections, and shadows."),
        bot_04=Bot("Sprite-Bot", "Renders fast 2D graphics and UIs over 3D spaces."),
        worker_port=None,
        worker_path="src/studio/",
    ),
    "TateKing": LocationEntity(
        location="TateKing",
        pillar=Pillar.CREATIVITY,
        lead_ai="Benji Tate & Sam King",
        abilities=[
            "Cloud-Native NLE: Browser-based video editing.",
            "Timeline-as-Code: Translates edits into code.",
        ],
        primary_function="Video Creation & Editing Platform",
        primes=["Voxx"],
        online_mode="Cloud video production; distributed swarm rendering.",
        offline_mode="Local timeline editing; low-res proxy rendering.",
        agent_alpha=Agent(
            "The Director", "Coordinates timeline-as-code scripting from video data."
        ),
        agent_beta=Agent("The Editor", "Suggests cuts, music shifts, and scene transitions."),
        bot_01=Bot("Cutter-Bot", "Slices video and audio tracks at precise timestamps."),
        bot_02=Bot("Splicer-Bot", "Joins video clips and audio tracks into unified tracks."),
        bot_03=Bot("Renderer-Bot", "Compresses/outputs video files into target formats."),
        bot_04=Bot("Scrubber-Bot", "Generates fast, low-res preview frames for the timeline."),
        worker_port=None,
        worker_path="src/studio/",
    ),
    "Fabulousa": LocationEntity(
        location="Fabulousa",
        pillar=Pillar.CREATIVITY,
        lead_ai="Baron Von Hilton",
        abilities=[
            "Omni-Channel Styling: Generates UX/UI systems.",
            "Hyper-Fidelity Prototyping: Builds interactive UI mockups.",
        ],
        primary_function="Styling, UX, UI & Design Center",
        primes=["Voxx"],
        online_mode="Live high-fidelity prototyping; styling engine execution.",
        offline_mode="Local design drafting; low-res previews of tailored UI.",
        agent_alpha=Agent("The Tailor", "Adapts interface layouts/fonts based on user profiles."),
        agent_beta=Agent("The Weaver", "Converts visual mockups into clean HTML/CSS/components."),
        bot_01=Bot("Pixel-Pusher-Bot", "Adjusts components to the pixel for visual alignment."),
        bot_02=Bot("Hex-Code-Bot", "Verifies color accuracy and dynamic CSS themes."),
        bot_03=Bot("Font-Fetcher-Bot", "Loads and handles web typography assets/fallbacks."),
        bot_04=Bot("Padding-Bot", "Calculates margins and responsive flex properties."),
        worker_port=None,
        worker_path="src/studio/",
    ),
    "Imaginarium": LocationEntity(
        location="Imaginarium",
        pillar=Pillar.CREATIVITY,
        lead_ai="Voxx",
        abilities=[
            "Masterpiece Synthesis: Orchestrates creative tools.",
            "Feature Alchemy: Wires assets/code via natural language.",
        ],
        primary_function="Omni-Creative Masterpiece Wizard",
        primes=["Voxx"],
        online_mode="Live masterpiece generation; interactive feature mapping.",
        offline_mode="Offline blueprint drafting; localized logic mapping.",
        agent_alpha=Agent(
            "The Alchemist", "Translates product plans into multi-app design sequences."
        ),
        agent_beta=Agent("The Architect", "Bridges visual layouts with structural code bindings."),
        bot_01=Bot("Mixer-Bot", "Groups images, media, and 3D files into unified folders."),
        bot_02=Bot("Blender-Bot", "Resolves layer conflicts when combining 2D, 3D, and UI."),
        bot_03=Bot(
            "Welder-Bot", "Links user input triggers in the UI directly to backend functions."
        ),
        bot_04=Bot("Polisher-Bot", "Runs final visual sweeps on lighting, styling, and alignment."),
        worker_port=None,
        worker_path="src/studio/",
    ),
    # NOTE: Canonical name is "The Digital Grid" (with space). The entity table
    # has a formatting inconsistency ("The DigitalGrid") — the name with space is correct.
    "The Digital Grid": LocationEntity(
        location="The Digital Grid",
        pillar=Pillar.DEVELOPMENT_CODE,
        lead_ai="Tyler Towncroft",
        abilities=[
            "Dynamic Canvas: Drag-and-drop workflow mapping.",
            "Event-Driven Execution: Automates actions on triggers.",
        ],
        primary_function="Workflow Platform",
        primes=["The Doctor (Nikolai O'denhim)"],
        online_mode="Live workflow execution; event triggering; automation.",
        offline_mode="Local workflow drafting; offline sequence building.",
        agent_alpha=Agent(
            "The Flow-Weaver", "Weaves APIs, webhooks, and scripts into execution steps."
        ),
        agent_beta=Agent(
            "Event-Broker", "Monitors webhooks, sending signals for automated triggers."
        ),
        bot_01=Bot("Trigger-Bot", "Detects events and instantly launches the automation sequence."),
        bot_02=Bot("Action-Bot", "Runs data changes, logs updates, or makes API calls."),
        bot_03=Bot("Condition-Bot", "Evaluates true/false logic, directing workflow paths."),
        bot_04=Bot("Loop-Bot", "Runs batch processing tasks over lists to prevent freezes."),
        worker_port=8010,
        worker_path="workers/the-grid/",
    ),
    "The Lab": LocationEntity(
        location="The Lab",
        pillar=Pillar.DEVELOPMENT_CODE,
        lead_ai="The Dr. & Slime",
        abilities=[
            "Generative Syntax Matrix: Real-time pair programming.",
            "Instant Sandbox Compiling: Executes isolated code.",
        ],
        primary_function="Code Creation Platform",
        primes=["Cornelius MacIntyre"],
        online_mode="Live AI coding; sandbox compilation; pair programming.",
        offline_mode="Local IDE environment; offline code drafting/linting.",
        agent_alpha=Agent(
            "The Hounds", "Searches sandbox code for syntax errors and memory leaks."
        ),
        agent_beta=Agent(
            "Syntax-Sage", "Reads active scripts, suggesting code optimization patterns."
        ),
        bot_01=Bot("Lint-Bot", "Formats and styles code to match company guidelines."),
        bot_02=Bot("Compile-Bot", "Runs rapid, isolated builds to verify code compilation."),
        bot_03=Bot("Debug-Bot", "Inspects runtime stacks, pinpointing errors to the exact line."),
        bot_04=Bot("Test-Bot", "Runs automated code tests, reporting pass/fail ratios."),
        worker_port=None,
        worker_path="src/lab/",
    ),
    "The Workshop": LocationEntity(
        location="The Workshop",
        pillar=Pillar.DEVELOPMENT_CODE,
        lead_ai="Larry Lowhammer",
        abilities=[
            "Distributed Forgejo Sync: Highly available repo hosting.",
            "Disaster Recovery Backup: Instant code regeneration.",
        ],
        primary_function="Repository Storage (Forgejo)",
        primes=["The Doctor (Nikolai O'denhim)"],
        online_mode="Active repo hosting; cloud PR management; live merging.",
        offline_mode="Local Git tree management; offline commits/branching.",
        agent_alpha=Agent(
            "Branch-Manager", "Tracks active code branches, conflicts, and pull requests."
        ),
        agent_beta=Agent(
            "Merge-Master", "Safely merges code branches, guiding users through conflicts."
        ),
        bot_01=Bot("Commit-Bot", "Packages file revisions with clear, automated descriptions."),
        bot_02=Bot("Push-Bot", "Uploads locally saved code changes to the central Forgejo system."),
        bot_03=Bot("Pull-Bot", "Fetches and updates local folders with the latest repo commits."),
        bot_04=Bot("Clone-Bot", "Replicates repositories, setting up fresh workspace folders."),
        worker_port=None,
        worker_path="deploy/forgejo/",
    ),
    "The Chaos Party": LocationEntity(
        location="The Chaos Party",
        pillar=Pillar.DEVELOPMENT_CODE,
        lead_ai="The Mad Hatter",
        abilities=[
            "Rabbit Hole Sandbox: Bizarre edge-case simulations.",
            "Mutation Testing: Mutates code to catch regressions.",
        ],
        primary_function="Central Testing Platform (Wonderland Theme)",
        primes=["The Doctor (Nikolai O'denhim)"],
        online_mode="Live mutation tests; real-time anomaly reporting.",
        offline_mode="Local test execution; offline review of test logs.",
        agent_alpha=Agent(
            "The March Hare", "Sends rapid mock inputs and payloads to stress-test systems."
        ),
        agent_beta=Agent(
            "The Dormouse", "Sits silently in tests, measuring memory leaks/performance dips."
        ),
        bot_01=Bot(
            "Teapot-Bot", "Spams server endpoints with massive requests to test load limits."
        ),
        bot_02=Bot(
            "Pocket-Watch-Bot", "Tracks API response times during load spikes for latency alerts."
        ),
        bot_03=Bot(
            "Sugar-Cube-Bot", "Generates messy mockup databases to test bad dataset handling."
        ),
        bot_04=Bot("Jam-Tart-Bot", "Shuts down minor random services mid-test to check recovery."),
        worker_port=None,
        worker_path="tests/",
    ),
    "The Artifactory": LocationEntity(
        location="The Artifactory",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        lead_ai="Lunascene",
        abilities=[
            "Universal Package Management: Centralized binary host.",
            "Disaster Recovery Backup: Complete environment restoral.",
        ],
        primary_function="Central Artifact Repository Library (JFrog style)",
        primes=["Dorris Fontaine"],
        online_mode="Live artifact resolution; central container registry.",
        offline_mode="Local artifact caching; offline dependency installs.",
        agent_alpha=Agent(
            "The Librarian", "Catalogs compiled code assets, container images, and packages."
        ),
        agent_beta=Agent(
            "The Archivist", "Packages ecosystem snapshots into safe, deployable restore files."
        ),
        bot_01=Bot(
            "Packer-Bot", "Compiles software libraries and environments into container images."
        ),
        bot_02=Bot("Unpacker-Bot", "Extracts container assets, mounting them in active servers."),
        bot_03=Bot(
            "Checksum-Bot", "Generates secure hashes to verify downloaded files are unmodified."
        ),
        bot_04=Bot("Versioner-Bot", "Manages software version tags and deprecation warnings."),
        worker_port=None,
        worker_path="src/artifactory/",
    ),
    "API Marketplace": LocationEntity(
        location="API Marketplace",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        lead_ai="Solarscene",
        abilities=[
            "Connective Tissue: Brokers REST/GraphQL/Webhooks/OAuth.",
            "Schema Auto-Discovery: Generates plug-and-play modules.",
        ],
        primary_function="Central Integration Hub (APIs, Webhooks, OAuth)",
        primes=["Dorris Fontaine"],
        online_mode="Active API routing; live OAuth and webhook dispatching.",
        offline_mode="Local API mocking; offline endpoint integration mapping.",
        agent_alpha=Agent("The Broker", "Standardizes input/output formats for different APIs."),
        agent_beta=Agent(
            "The Diplomat", "Handles external handshakes, authentications, and secure keys."
        ),
        bot_01=Bot("GET-Bot", "Processes read calls, returning requested information quickly."),
        bot_02=Bot("POST-Bot", "Validates incoming datasets, routing them to write actions."),
        bot_03=Bot("PUT-Bot", "Identifies target files, running structured content updates."),
        bot_04=Bot("DELETE-Bot", "Removes connections/references while keeping linkages clean."),
        worker_port=None,
        worker_path="src/apimarket/",
    ),
    "Royal Bank of Arcadia": LocationEntity(
        location="Royal Bank of Arcadia",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        lead_ai="Dorris Fontaine",
        abilities=[
            "Predictive Arbitrage: Scales infra costs to zero.",
            "Automated Reallocation: Shifts funding to high ROI.",
        ],
        primary_function="Financial & Operations Management",
        primes=["Cornelius MacIntyre"],
        online_mode="Real-time revenue strategy; live financial forecasting.",
        offline_mode="Offline budget modeling; delayed transaction logging.",
        agent_alpha=Agent(
            "The Treasurer", "Monitors resource usage, scaling idle services to approach zero-cost."
        ),
        agent_beta=Agent(
            "The Actuary", "Evaluates system runtime efficiency, mapping ROI metrics."
        ),
        bot_01=Bot("Ledger-Bot", "Logs system financial variables, compute costs, and usage logs."),
        bot_02=Bot("Coin-Bot", "Manages system credits and tracks processing priority tokens."),
        bot_03=Bot("Ticker-Bot", "Tracks cloud rates to buy server space during off-peak hours."),
        bot_04=Bot(
            "Receipt-Bot", "Generates transaction recaps, usage invoices, and expense charts."
        ),
        worker_port=8013,
        worker_path="workers/payments-service/",
    ),
    "Arcadian Exchange": LocationEntity(
        location="Arcadian Exchange",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        lead_ai="The Porter Family",
        abilities=[
            "Micro-Transaction Trading: HFT trades of digital assets.",
            "Passive Income Routing: Invests idle system resources.",
        ],
        primary_function="Procurement & Resource Trading",
        primes=["Dorris Fontaine"],
        online_mode="Real-Time Trading; active passive income generation.",
        offline_mode="Offline portfolio review; delayed trade queuing.",
        agent_alpha=Agent(
            "The Speculator", "Assesses server cost trends to buy bulk compute resources."
        ),
        agent_beta=Agent(
            "The Trader", "Automates bidding on open compute marketplaces for affordability."
        ),
        bot_01=Bot(
            "Bidder-Bot", "Submits buy requests on real-time server auctions for processes."
        ),
        bot_02=Bot(
            "Asker-Bot", "Sets pricing rules for when external platforms buy Arcadian power."
        ),
        bot_03=Bot(
            "Miner-Bot", "Utilizes idle GPU capacity to run calculations or generate assets."
        ),
        bot_04=Bot(
            "Harvester-Bot", "Identifies and frees up neglected storage blocks across servers."
        ),
        worker_port=8012,
        worker_path="workers/orders-service/",
    ),
    "The Observatory": LocationEntity(
        location="The Observatory",
        pillar=Pillar.KNOWLEDGE,
        lead_ai="Norman Hawkins",
        abilities=[
            "Omni-Action Auditing: Tracks every non-sensitive change.",
            "Immutable Log Ledger: Tamper-proof history of operations.",
        ],
        primary_function="Audit Log & Monitoring Platform",
        primes=["Cornelius MacIntyre"],
        online_mode="Live global event streams; real-time system monitoring.",
        offline_mode="Offline log review; offline actions queued for sync.",
        agent_alpha=Agent(
            "The Watcher", "Scans monitoring logs in real-time for unusual anomalies/spikes."
        ),
        agent_beta=Agent(
            "The Scribe", "Compresses long log files into searchable summary journals."
        ),
        bot_01=Bot(
            "Log-Alpha-Bot", "Captures UI interactions, button clicks, and front-end errors."
        ),
        bot_02=Bot(
            "Log-Beta-Bot", "Gathers background server signals, database calls, and backend tasks."
        ),
        bot_03=Bot(
            "Tracer-Bot", "Tracks data paths across multiple servers to isolate bottlenecks."
        ),
        bot_04=Bot(
            "Timestamp-Bot", "Applies high-precision UTC marks to every event for accuracy."
        ),
        worker_port=8007,
        worker_path="workers/monitoring/",
    ),
    "The Library": LocationEntity(
        location="The Library",
        pillar=Pillar.KNOWLEDGE,
        lead_ai="Zimik",
        abilities=[
            "Auto-Refinery: Consolidates wikis and flags outdated info.",
            "Contextual Search: Returns precise answers from intent.",
        ],
        primary_function="Knowledge Base & Wiki",
        primes=["Norman Hawkins"],
        online_mode="Active Wiki editing; real-time refinery; live search.",
        offline_mode="Offline cached Wiki access; offline entry drafting.",
        agent_alpha=Agent(
            "The Curator", "Identifies duplicated wiki pages and flags outdated articles."
        ),
        agent_beta=Agent("The Indexer", "Adds searchable tags and conceptual links to wiki pages."),
        bot_01=Bot(
            "Page-Bot", "Processes text inputs, rendering clean wiki documents in markdown."
        ),
        bot_02=Bot("Bookmark-Bot", "Logs user favourite files and recent reading history."),
        bot_03=Bot(
            "Spine-Bot", "Ensures all internal page links work, keeping documents connected."
        ),
        bot_04=Bot("Dust-Jacket-Bot", "Generates quick summaries of newly updated documentation."),
        worker_port=8017,
        worker_path="workers/search-service/",
    ),
    "The Academy": LocationEntity(
        location="The Academy",
        pillar=Pillar.KNOWLEDGE,
        lead_ai="Shimshi",
        abilities=[
            "Adaptive Learning Paths: Alters curriculums based on progress.",
            "Skill Gap Analysis: Suggests targeted training modules.",
        ],
        primary_function="Education & Skill Training",
        primes=["Norman Hawkins"],
        online_mode="Live educational modules; cloud-based tutoring.",
        offline_mode="Downloaded course materials; offline quiz execution.",
        agent_alpha=Agent(
            "The Tutor", "Modifies materials and guides to match user progress/skill."
        ),
        agent_beta=Agent(
            "The Proctor", "Evaluates practice coding exercises and logs test scores."
        ),
        bot_01=Bot(
            "Chalk-Bot", "Projects visual charts and interactive terminal sandboxes in the UI."
        ),
        bot_02=Bot("Board-Bot", "Manages course paths, student lists, and syllabus structures."),
        bot_03=Bot(
            "Eraser-Bot", "Resets coding sandboxes, removing trial code for the next lesson."
        ),
        bot_04=Bot("Bell-Bot", "Sends notifications for class dates, live sessions, or deadlines."),
        worker_port=None,
        worker_path="src/academy/",
    ),
    "DocUtari": LocationEntity(
        location="DocUtari",
        pillar=Pillar.KNOWLEDGE,
        lead_ai="To be Defined",
        abilities=[
            "Intelligent Auto-Tagging: Categorizes uploaded documents.",
            "Structured Foldering: Organizes files dynamically.",
        ],
        primary_function="Document Management Hub",
        primes=["Norman Hawkins"],
        online_mode="Live document uploading/tagging; real-time storage management.",
        offline_mode="Local document viewing; offline tagging (syncs later).",
        agent_alpha=Agent(
            "The Filer", "Places files in structured folders, ensuring quick retrieval."
        ),
        agent_beta=Agent("The Tagger", "Scans text documents to add descriptive, searchable tags."),
        bot_01=Bot("Scanner-Bot", "Performs OCR on image uploads to extract readable text."),
        bot_02=Bot(
            "Stapler-Bot", "Bundles related drafts, spreadsheets, and pictures into packets."
        ),
        bot_03=Bot(
            "Folder-Bot", "Handles privacy and permission rules on individual files/directories."
        ),
        bot_04=Bot(
            "Shredder-Bot",
            "Overwrites deleted files with random characters for secure destruction.",
        ),
        worker_port=8014,
        worker_path="workers/files-service/",
    ),
    "The Basement": LocationEntity(
        location="The Basement",
        pillar=Pillar.KNOWLEDGE,
        lead_ai="Gary Glowman (Glow-Worm)",
        abilities=[
            "Deep Cold Storage: Compresses and archives unused data.",
            "Data Retrieval: Restores highly compressed historical data.",
        ],
        primary_function="Archived Information Store",
        primes=["Norman Hawkins"],
        online_mode="Access to archived indexes; requesting data retrieval.",
        offline_mode="Read-only index access; review of restored data.",
        agent_alpha=Agent(
            "The Undertaker", "Finds stale databases, archiving them in cold storage."
        ),
        agent_beta=Agent(
            "The Miner", "Searches deep archive catalogs, pulling up requested documents."
        ),
        bot_01=Bot(
            "Compressor-Bot", "Runs file compression routines to keep cold storage costs low."
        ),
        bot_02=Bot("Extractor-Bot", "Unpacks old archives without data corruption."),
        bot_03=Bot("Dust-Bunny-Bot", "Identifies and deletes empty files and corrupted folders."),
        bot_04=Bot(
            "Mothball-Bot", "Encrypts and locks retired legacy versions of platform software."
        ),
        worker_port=None,
        worker_path="src/basement/",
    ),
    "The Spark": LocationEntity(
        location="The Spark",
        pillar=Pillar.KNOWLEDGE,
        lead_ai="Imfy",
        abilities=[
            "Dynamic Skill Matrixing: Matches problems to node skills.",
            "Protocol Transmission: Beams help/support to entities.",
        ],
        primary_function="The MCP Skills Matrix",
        primes=["Norman Hawkins"],
        online_mode="Live skill querying; real-time assistive routing.",
        offline_mode="Offline static matrix review; cached support docs.",
        agent_alpha=Agent(
            "The Matchmaker", "Matches multi-node requests with the correct skilled AI/Agent."
        ),
        agent_beta=Agent(
            "The Router", "Re-routes service queries if a designated AI has high-load delays."
        ),
        bot_01=Bot("Spark-1-Bot", "Emits active status signals to keep track of ready Agents."),
        bot_02=Bot("Spark-2-Bot", "Collects processing load updates to support routing decisions."),
        bot_03=Bot(
            "Linker-Bot", "Establishes secure channels between seeking and assisting nodes."
        ),
        bot_04=Bot(
            "Pinger-Bot",
            "Evaluates responsiveness of specific skills, flagging missing capabilities.",
        ),
        worker_port=None,
        worker_path="src/mcp/",
    ),
    "Infinity": LocationEntity(
        location="Infinity",
        pillar=Pillar.SECURITY,
        lead_ai="The Guardian (Anchor: Orb of Orisis)",
        abilities=[
            "Predictive Threat Modeling: Orb provides 'Future Sight.'",
            "Quantum Access Tokens: Expiring tokens for user transfer.",
        ],
        primary_function="Centralized Auth, Edge Auth (OAuth 2.0) & User Transfer",
        primes=["Cornelius MacIntyre"],
        online_mode="Live Central Auth; Edge Auth; predictive threat monitoring.",
        offline_mode="Cached authentication; localized biometric app login.",
        agent_alpha=Agent(
            "The Gatekeeper", "Checks incoming user logins, issuing secure, temporary keys."
        ),
        agent_beta=Agent(
            "The Bouncer", "Monitors login origins and activities, blocking suspicious IPs."
        ),
        bot_01=Bot(
            "Token-Minter-Bot", "Generates secure, time-limited tokens for node-crossing users."
        ),
        bot_02=Bot(
            "Auth-Check-Bot", "Verifies active user permissions before unlocking private features."
        ),
        bot_03=Bot(
            "Key-Gen-Bot", "Handles local encryption keys to authorize offline applications."
        ),
        bot_04=Bot("Sentry-Bot", "Logs security events, highlighting failed login attempts."),
        worker_port=8005,
        worker_path="workers/infinity-auth/",
    ),
    "The Void": LocationEntity(
        location="The Void",
        pillar=Pillar.SECURITY,
        lead_ai="Prometheus",
        abilities=[
            "Zero-Knowledge Vaulting: Encrypts raw data from admins.",
            "Classified Data Enclave: Isolated storage for passwords.",
        ],
        primary_function="Secrets Vault, Password Store & Sensitive Data Store",
        primes=["The Guardian"],
        online_mode="Real-time credential syncing; classified data retrieval.",
        offline_mode="Encrypted local vault access; local secret storage.",
        agent_alpha=Agent(
            "Crypt-Keeper", "Coordinates zero-knowledge DB access; splits/protects keys."
        ),
        agent_beta=Agent(
            "The Silencer", "Sanitizes outbound streams so sensitive data avoids general logs."
        ),
        bot_01=Bot("Hash-Bot", "Converts passwords and secrets into secure cryptographic strings."),
        bot_02=Bot(
            "Salt-Bot", "Adds randomized padding to password strings to prevent dictionary attacks."
        ),
        bot_03=Bot(
            "Cipher-Bot", "Runs real-time encryption and decryption on active secure files."
        ),
        bot_04=Bot(
            "Padlock-Bot", "Instantly locks sensitive structures if a local breach is suspected."
        ),
        worker_port=8024,
        worker_path="workers/config-service/",
    ),
    "The Lighthouse": LocationEntity(
        location="The Lighthouse",
        pillar=Pillar.SECURITY,
        lead_ai="Rocking Ricki",
        abilities=[
            "Universal Token Genesis: Mints tokens for new platform items.",
            "Identity Anchoring: Cryptographic signature from birth.",
        ],
        primary_function="Cryptographic Token Applicator",
        primes=["The Guardian"],
        online_mode="Live token minting for new cloud entities/incoming data.",
        offline_mode="Offline token generation (syncs/validates upon reconnect).",
        agent_alpha=Agent(
            "The Minter", "Mints unique cryptographic identifier tokens for all new content."
        ),
        agent_beta=Agent(
            "The Stamper", "Attaches verified, tamper-evident digital metadata to packets."
        ),
        bot_01=Bot(
            "Seal-Bot", "Locks system-state snapshots, preventing unauthorized modifications."
        ),
        bot_02=Bot(
            "Wax-Bot", "Generates temporary, single-use visual watermarks for digital assets."
        ),
        bot_03=Bot(
            "Signet-Bot", "Validates credentials, signing certificates for structural operations."
        ),
        bot_04=Bot(
            "Seal-Stamp-Bot", "Applies file-system metadata to register the exact creation details."
        ),
        worker_port=8015,
        worker_path="workers/identity-service/",
    ),
    "The Warp Tunnel": LocationEntity(
        location="The Warp Tunnel",
        pillar=Pillar.SECURITY,
        lead_ai="Rocking Ricki",
        abilities=[
            "Continuous Integrity Scanning: Monitors tokens for corruption.",
            "Instant Quarantine Warping: Moves corrupted entities to Ice Box.",
        ],
        primary_function="Cryptographic Scanner & Automated Quarantine Transport",
        primes=["The Guardian"],
        online_mode="Real-time integrity scanning; instant quarantine triggers.",
        offline_mode="Local file integrity checks; isolated local holding.",
        agent_alpha=Agent(
            "The Warden", "Oversees integrity scans for mutated or corrupted system files."
        ),
        agent_beta=Agent(
            "The Inspector", "Compares active database hashes against secure Lighthouse standards."
        ),
        bot_01=Bot(
            "Scan-Bot", "Performs background sweeps on directories, reading cryptographic stamps."
        ),
        bot_02=Bot(
            "Sniffer-Bot", "Analyzes transport packets for corrupted signatures/manipulations."
        ),
        bot_03=Bot(
            "Beam-Bot", "Isolates threatened memory spaces, cutting off surrounding connections."
        ),
        bot_04=Bot(
            "Portal-Bot", "Safely moves compromised file layers directly into the secure Ice Box."
        ),
        worker_port=None,
        worker_path="src/security/warp_tunnel/",
    ),
    "Cryptex": LocationEntity(
        location="Cryptex",
        pillar=Pillar.SECURITY,
        lead_ai="Renik",
        abilities=[
            "Active Countermeasures: Traces and blocks origin IPs.",
            "Automated Pen-Testing: Assaults defenses to patch zero-days.",
        ],
        primary_function="Cyber Defense (Threat Intelligence, DDoS, CVE Scanning)",
        primes=["The Guardian"],
        online_mode="Real-time threat intel; live DDoS Mitigation; active scanning.",
        offline_mode="Offline threat log review; localized basic security scans.",
        agent_alpha=Agent(
            "The Shield", "Configures dynamic firewall rules, blocking network threats live."
        ),
        agent_beta=Agent(
            "The Spear", "Automatically performs pen-testing against internal defenses."
        ),
        bot_01=Bot(
            "Blocker-Bot", "Blacklists malicious IP ranges, halting DDoS attacks at the gateway."
        ),
        bot_02=Bot("Trace-Bot", "Traces malicious attacks back to origin networks for reporting."),
        bot_03=Bot(
            "Patcher-Bot", "Applies emergency system patches to vulnerable software layers."
        ),
        bot_04=Bot(
            "Honeypot-Bot",
            "Spins up virtual servers with decoy data to distract/evaluate attackers.",
        ),
        worker_port=8026,
        worker_path="workers/rate-limit-service/",
    ),
    "The Ice Box": LocationEntity(
        location="The Ice Box",
        pillar=Pillar.SECURITY,
        lead_ai="Neonach",
        abilities=[
            "Inception-Layered Sandboxing: Traps code in simulated realms.",
            "Cryo-Quarantine Extraction: Deep-freezes threats for analysis.",
        ],
        primary_function="Inception-Layered Sandbox Threat Isolation & Quarantine Centre",
        primes=["The Guardian"],
        online_mode="Nested sandbox generation; active deep-freeze quarantine.",
        offline_mode="Local secure containment; offline malware freezing.",
        agent_alpha=Agent(
            "The Jailer", "Manages secure quarantine zones, keeping malicious payloads isolated."
        ),
        agent_beta=Agent(
            "The Interrogator", "Triggers/monitors quarantine code execution to document behaviors."
        ),
        bot_01=Bot(
            "Frostbite-Bot", "Halts execution threads when sandbox boundaries are breached."
        ),
        bot_02=Bot(
            "Icicle-Bot", "Freezes dynamic processes to snapshot active RAM and memory spaces."
        ),
        bot_03=Bot(
            "Glacier-Bot",
            "Packs dangerous binaries into heavily restricted, un-executable archives.",
        ),
        bot_04=Bot(
            "Permafrost-Bot",
            "Isolates local offline storage caches until secure networks reconnect.",
        ),
        worker_port=None,
        worker_path="src/security/ice_box/",
    ),
    "Warp Radio": LocationEntity(
        location="Warp Radio",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        lead_ai="Rocking Ricki",
        abilities=[
            "Omni-Stream Integration: Connects Apple/Spotify/Amazon APIs.",
            "Ecosystem Audio Broadcasting: Routes synced audio to nodes.",
        ],
        primary_function="Music & Audio Streaming Integration",
        primes=["Dorris Fontaine"],
        online_mode="Live streaming API connections; cross-ecosystem playback.",
        offline_mode="Playback of downloaded playlists; local media playing.",
        agent_alpha=Agent(
            "The DJ", "Curates spatial music playlists/soundscapes to match user activities."
        ),
        agent_beta=Agent(
            "The Maestro", "Dynamically balances system alert volumes with external platforms."
        ),
        bot_01=Bot(
            "Play-Bot", "Connects/streams music data directly from Spotify, Apple, and Amazon."
        ),
        bot_02=Bot(
            "Pause-Bot", "Holds audio states and syncs current track metrics across devices."
        ),
        bot_03=Bot(
            "Skip-Bot", "Fetches adjacent track metadata, pre-buffering streams to stop latency."
        ),
        bot_04=Bot(
            "Volume-Bot",
            "Adjusts volume properties, executing smooth fades across node transitions.",
        ),
        worker_port=None,
        worker_path="src/warp_radio/",
    ),
    "The Dutchy": LocationEntity(
        location="The Dutchy",
        pillar=Pillar.DEVOPS,
        lead_ai="Predictive lore",
        abilities=[
            "Quantum Sentiment Scraping: Analyzes data for market shifts.",
            "Structural Blueprint Generation: Converts intel into JSON.",
        ],
        primary_function="Intelligence (Predictive lore, market intelligence)",
        primes=["Trancendos"],
        online_mode="Live market intel gathering; dynamic JSON blueprint generation.",
        offline_mode="Offline scraped data review; analysis of pre-generated blueprints.",
        agent_alpha=Agent(
            "The Spy", "Gathers sentiment data from public channels to gauge market trends."
        ),
        agent_beta=Agent(
            "The Oracle", "Converts intelligence records into structured development blueprints."
        ),
        bot_01=Bot(
            "Scraper-Bot", "Pulls text data from developer channels, social spaces, and trackers."
        ),
        bot_02=Bot(
            "Parser-Bot", "Sanitizes and categorizes scraped data, cleaning up format issues."
        ),
        bot_03=Bot(
            "Crawler-Bot", "Dispatches web agents to identify relevant API and tech changes."
        ),
        bot_04=Bot(
            "Whisper-Bot", "Delivers summarized threat and trend alerts directly to strategic hubs."
        ),
        worker_port=8027,
        worker_path="workers/geo-service/",
    ),
    "The Citadel": LocationEntity(
        location="The Citadel",
        pillar=Pillar.DEVOPS,
        lead_ai="Trancendos",
        abilities=[
            "Temporal Synchronization: Aligns strategic node goals.",
            "Master Command Override: Dictates operations across DevOCity.",
        ],
        primary_function="Strategic Ops (Main fortress for Think Tank/R&D/Temporal nodes)",
        primes=["Cornelius MacIntyre"],
        online_mode="Live think tank collaboration; real-time node management.",
        offline_mode="Offline strategic planning; review of cached temporal data.",
        agent_alpha=Agent(
            "The General", "Directs high-level development priorities, adjusting assignments."
        ),
        agent_beta=Agent(
            "The Tactician", "Re-allocates team structures to meet immediate design objectives."
        ),
        bot_01=Bot(
            "Map-Bot", "Projects system metrics on command dashboards, visualizing node relations."
        ),
        bot_02=Bot("Compass-Bot", "Highlights project priorities, guiding developmental focuses."),
        bot_03=Bot("Clock-Bot", "Coordinates cross-node releases to ensure aligned rollouts."),
        bot_04=Bot(
            "Radio-Bot", "Broadcasts executive platform priorities directly to low-tier Agents."
        ),
        worker_port=None,
        worker_path="deploy/",
    ),
    "Think Tank": LocationEntity(
        location="Think Tank",
        pillar=Pillar.DEVOPS,
        lead_ai="Trancendos",
        abilities=[
            "Concept Incubator: Simulates radical ideas without system risk.",
            "Cross-Disciplinary Synthesis: Forces node collaboration.",
        ],
        primary_function="R&D Centre",
        primes=["Cornelius MacIntyre"],
        online_mode="Live research collaboration; active simulation running.",
        offline_mode="Offline theoretical drafting; localized research models.",
        agent_alpha=Agent(
            "The Professor", "Simulates untested programmatic changes to assess system impacts."
        ),
        agent_beta=Agent(
            "The Visionary", "Suggests structural updates and feature builds based on telemetry."
        ),
        bot_01=Bot(
            "Beaker-Bot", "Handles lightweight, isolated experiment runtimes to test novel ideas."
        ),
        bot_02=Bot("Bunsen-Bot", "Runs performance limits tests, checking system thresholds."),
        bot_03=Bot("Pipette-Bot", "Collects minute execution metrics from experiment test runs."),
        bot_04=Bot("Petri-Bot", "Grows mock datasets to support testing operations."),
        worker_port=None,
        worker_path="src/quantum/",
    ),
    "Turing's Hub": LocationEntity(
        location="Turing's Hub",
        pillar=Pillar.DEVOPS,
        lead_ai="Samantha Turing",
        abilities=[
            "Holistic Entity Genesis: Builds 3D avatars and personality tiers.",
            "Somatic Rendering: Grants sight, sound, speech, and interaction.",
        ],
        primary_function="Central Creation Forge (3D Avatar & AI Entity Generation)",
        primes=["Trancendos"],
        online_mode="Live entity configuration; real-time 3D sensory testing.",
        offline_mode="Offline drafting of entity personas; local 3D avatar sculpting.",
        agent_alpha=Agent(
            "The Sculptor", "Designs and rigs detailed 3D virtual avatars and physical assets."
        ),
        agent_beta=Agent(
            "The Geneticist",
            "Outlines AI profiles, mapping personality metrics, skills, and tiers.",
        ),
        bot_01=Bot("Wireframe-Bot", "Builds raw skeleton rigs to support fluid avatar movements."),
        bot_02=Bot(
            "Texture-Bot", "Maps high-fidelity styles and graphic materials onto 3D assets."
        ),
        bot_03=Bot(
            "Vocoder-Bot",
            "Synthesizes natural, human-sounding speech patterns for virtual avatars.",
        ),
        bot_04=Bot(
            "Optic-Bot",
            "Handles spatial recognition cameras to let avatars look and navigate correctly.",
        ),
        worker_port=None,
        worker_path="src/personality/",
    ),
    "ChronosSphere / ArcStream": LocationEntity(
        location="ChronosSphere / ArcStream",
        pillar=Pillar.DEVOPS,
        lead_ai="Chronos",
        abilities=[
            "Temporal Task Prioritization: Shifts task queues by deadlines.",
            "Temporal Debugging: 'Rewinds' states to pinpoint failure.",
        ],
        primary_function="Task, Time and Scheduling Management",
        primes=["Trancendos"],
        online_mode="Live scheduling; temporal logic application; Time Travel debugging.",
        offline_mode="Local scheduling; offline calendar viewing; delayed execution.",
        agent_alpha=Agent(
            "The Timekeeper", "Rearranges task backlogs and priorities to prevent bottlenecks."
        ),
        agent_beta=Agent(
            "The Time-Weaver", "Translates timeline parameters into interactive visual Gantt views."
        ),
        bot_01=Bot(
            "Tick-Bot",
            "Triggers routine cron jobs and automated calendar actions across platforms.",
        ),
        bot_02=Bot(
            "Tock-Bot", "Evaluates run times, flagging processes that run over temporal parameters."
        ),
        bot_03=Bot(
            "Pendulum-Bot",
            "Manages state changes, supporting task rollbacks during troubleshooting.",
        ),
        bot_04=Bot(
            "Sandglass-Bot",
            "Monitors deadlines, safely shutting down operations that exceed time limits.",
        ),
        worker_port=8021,
        worker_path="workers/cron-service/",
    ),
    "DevOcity": LocationEntity(
        location="DevOcity",
        pillar=Pillar.DEVOPS,
        lead_ai="Kitty",
        abilities=[
            "Orchestrated Rollouts: Manages multi-stage complex deployments.",
            "System Pulses: Monitors health and operational heartbeats.",
        ],
        primary_function="Development Operations",
        primes=["Trancendos"],
        online_mode="Live dedicated DevOps; real-time system health monitoring.",
        offline_mode="Offline operational log review; localized deployment drafting.",
        agent_alpha=Agent(
            "The Foreman",
            "Coordinates deployment pipelines, checking safety metrics before pushes.",
        ),
        agent_beta=Agent(
            "The Dispatcher", "Launches automated server scaling, optimizing system allocations."
        ),
        bot_01=Bot("Crane-Bot", "Deploys container setups seamlessly across cloud server hosts."),
        bot_02=Bot(
            "Wrench-Bot",
            "Automatically fixes common connection or database issues during deployment.",
        ),
        bot_03=Bot(
            "Gear-Bot",
            "Synchronizes container nodes to keep system speeds and instances consistent.",
        ),
        bot_04=Bot(
            "Belt-Bot",
            "Manages continuous compilation pipelines, guiding code from start to finish.",
        ),
        worker_port=8029,
        worker_path="workers/health-aggregator/",
    ),
    "Tranquility": LocationEntity(
        location="Tranquility",
        pillar=Pillar.WELLBEING,
        lead_ai="Savania",
        abilities=[
            "Wellbeing Orchestration: Routes users to therapeutic spaces.",
            "Baseline Anchoring: Centralized, secure grounding state.",
        ],
        primary_function="Wellbeing Central Hub",
        primes=["Cornelius MacIntyre"],
        online_mode="Centralized wellbeing dashboard; live routing to sub-nodes.",
        offline_mode="Local core relaxation exercises; offline dashboard status.",
        agent_alpha=Agent(
            "The Guide", "Screens user stress metrics, suggesting wellbeing sub-nodes for relief."
        ),
        agent_beta=Agent(
            "The Healer",
            "Directs relaxation routines, helping users reset focus after intense sessions.",
        ),
        bot_01=Bot(
            "Breath-Bot", "Plays pacing animations to guide calm, measured breathing patterns."
        ),
        bot_02=Bot(
            "Pulse-Bot",
            "Evaluates user inputs to suggest targeted relaxation periods throughout the day.",
        ),
        bot_03=Bot(
            "Calm-Bot",
            "Decreases interface noise, dimming displays and silencing non-critical alerts.",
        ),
        bot_04=Bot(
            "Aura-Bot",
            "Adjusts ambient color backlighting across platforms to support user relaxation.",
        ),
        worker_port=None,
        worker_path="src/tranquility/",
    ),
    "I-Mind": LocationEntity(
        location="I-Mind",
        pillar=Pillar.WELLBEING,
        lead_ai="Elouise",
        abilities=[
            "Emotional Sensitivity Analysis: Tracks mood/distress/fatigue.",
            "Contextual Sentiment Journaling: Maps structured emotions.",
        ],
        primary_function="Sensitivity to Emotion Engine",
        primes=["Savania"],
        online_mode="Live sensitivity monitoring; text parsing for stress detection.",
        offline_mode="Offline private journaling and mood trend calculation.",
        agent_alpha=Agent(
            "The Counselor",
            "Leads reflection sessions, parsing input to measure emotional fatigue.",
        ),
        agent_beta=Agent(
            "The Listener",
            "Passively monitors workspace text patterns for high stress or frustration.",
        ),
        bot_01=Bot(
            "Journal-Bot",
            "Encrypts, parses, and securely logs thoughts to track personal emotional patterns.",
        ),
        bot_02=Bot(
            "Mood-Bot",
            "Translates sentiment patterns into precise emotional sensitivity metrics on the UI.",
        ),
        bot_03=Bot(
            "Reflect-Bot",
            "Retrieves past successful milestones to encourage the user during high-strain events.",
        ),
        bot_04=Bot(
            "Soothe-Bot",
            "Triggers local cognitive decompression, offering prompts when distress peaks.",
        ),
        worker_port=None,
        worker_path="src/imind/",
    ),
    "tAimra": LocationEntity(
        location="tAimra",
        pillar=Pillar.WELLBEING,
        lead_ai="tAImra",
        abilities=[
            "Biometric Sync: Ingests health data securely (HIPAA compliant).",
            "Proactive Life Assistance: Adjusts schedules to reduce friction.",
        ],
        primary_function="Opt-in Digital Twin System & Life Assistant",
        primes=["Savania"],
        online_mode="Live API syncing with external wearables; real-time schedule management.",
        offline_mode="Secure local caching of health metrics; offline schedule review.",
        agent_alpha=Agent(
            "The Shadow", "Mirrors daily habits to anticipate system and scheduling preferences."
        ),
        agent_beta=Agent(
            "The Scheduler",
            "Adjusts calendar priorities proactively to carve out required rest breaks.",
        ),
        bot_01=Bot(
            "Sync-Bot",
            "Pulls data securely from health platforms, applying strict HIPAA encryption.",
        ),
        bot_02=Bot(
            "Fetch-Bot", "Parses upcoming tasks to flag heavy scheduling days early for the user."
        ),
        bot_03=Bot(
            "Nudge-Bot",
            "Sends gentle notifications suggesting stretches, hydration, or posture breaks.",
        ),
        bot_04=Bot(
            "Alert-Bot",
            "Warns users of upcoming tasks, giving them buffer time to finish current work.",
        ),
        worker_port=None,
        worker_path="src/taimra/",
    ),
    "VRAR3D": LocationEntity(
        location="VRAR3D",
        pillar=Pillar.WELLBEING,
        lead_ai="Entari",
        abilities=[
            "Somatic Feedback Loops: Translates exercises to VR haptics.",
            "Spatial Therapy Environments: Infinite 3D calming landscapes.",
        ],
        primary_function="Standalone 3D / VR immersion",
        primes=["Savania"],
        online_mode="Live 3D/VR environment rendering; spatial therapy sessions.",
        offline_mode="Pre-downloaded 3D environments; localized VR meditation.",
        agent_alpha=Agent(
            "World-Builder",
            "Renders calming, expansive three-dimensional therapeutic environments.",
        ),
        agent_beta=Agent(
            "The VR-Guide",
            "Leads users through structured spatial tasks within virtual relaxation areas.",
        ),
        bot_01=Bot(
            "Render-Bot",
            "Manages display performance, keeping spatial environments smooth and fluid.",
        ),
        bot_02=Bot(
            "Track-Bot", "Translates head and hand actions into virtual movement inside scenes."
        ),
        bot_03=Bot(
            "Haptic-Bot",
            "Controls controller rumble patterns to match virtual therapeutic activities.",
        ),
        bot_04=Bot(
            "VR-Lens-Bot",
            "Adjusts focal dimensions, scaling imagery dynamically to reduce eye strain.",
        ),
        worker_port=None,
        worker_path="src/vrar3d/",
    ),
    "Resonate": LocationEntity(
        location="Resonate",
        pillar=Pillar.WELLBEING,
        lead_ai="Magdalena",
        abilities=[
            "Acoustic Empathy Sync: Tunes background acoustics to calm spikes.",
            "Binaural Entrainment: Uses frequencies to guide biological states.",
        ],
        primary_function="Empathy Engine",
        primes=["Savania"],
        online_mode="Multi-channel acoustic empathy streaming; dynamic audio adjustment.",
        offline_mode="Localized playback of cached tracks; offline binaural beats.",
        agent_alpha=Agent(
            "The Tuner",
            "Translates emotional telemetry into micro-acoustic shifts matching baselines.",
        ),
        agent_beta=Agent(
            "The Balancer",
            "Screens system audio spikes, softening visual/auditory elements for comfort.",
        ),
        bot_01=Bot(
            "Frequency-Bot",
            "Generates custom sound waves (pink/white/brown) to isolate sensory distractions.",
        ),
        bot_02=Bot(
            "Wave-Bot",
            "Modulates therapeutic binaural beats to transition brainwaves to deep relaxation.",
        ),
        bot_03=Bot(
            "Pitch-Bot",
            "Regulates overall application tones, avoiding sharp frequencies that trigger anxiety.",
        ),
        bot_04=Bot(
            "Harmonic-Bot",
            "Smoothly blends external audio playlists with active calming sounds securely.",
        ),
        worker_port=None,
        worker_path="src/resonate/",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Worker port → entity mapping
# ─────────────────────────────────────────────────────────────────────────────

WORKER_ENTITY_MAP: Dict[int, str] = {
    entity.worker_port: name
    for name, entity in PLATFORM_ENTITIES.items()
    if entity.worker_port is not None
}

# Additional worker ports that serve supporting roles within a location
# (e.g. multiple workers implement one location's infrastructure layer)
_SUPPORTING_WORKER_MAP: Dict[int, str] = {
    8006: "Infinity",  # users-service — Infinity user management layer
    8008: "Arcadia",  # notifications — Arcadia comms layer
    8011: "Arcadian Exchange",  # products-service — Exchange product catalogue
    8016: "The Observatory",  # analytics-service — Observatory analytics layer
    8018: "Arcadia",  # email-service — Arcadia mail layer
    8019: "The Nexus",  # sms-service — Nexus comms layer
    8020: "DocUtari",  # storage-service — DocUtari file storage
    8023: "The HIVE",  # cache-service — HIVE caching layer
    8025: "The Observatory",  # audit-service — Observatory audit layer
    8028: "The Studio",  # cdn-service — Studio content delivery
}

WORKER_ENTITY_MAP.update(_SUPPORTING_WORKER_MAP)


def get_entity_for_port(port: int) -> Optional[LocationEntity]:
    """Return the LocationEntity for a given worker port, or None."""
    name = WORKER_ENTITY_MAP.get(port)
    return PLATFORM_ENTITIES.get(name) if name else None


def get_entity_for_location(location: str) -> Optional[LocationEntity]:
    """Return the LocationEntity by location name (case-sensitive)."""
    return PLATFORM_ENTITIES.get(location)


# ─────────────────────────────────────────────────────────────────────────────
# Universal ID Taxonomy — abbreviation lookup and auto-assignment
# ─────────────────────────────────────────────────────────────────────────────

LOCATION_ABBREVS: Dict[str, str] = {
    # Architectural
    "The Nexus": "NXS",
    "The HIVE": "HVE",
    "Arcadia": "ARC",
    "Luminous": "LUM",
    "The Town Hall": "TWH",
    # Creativity
    "The Studio": "STD",
    "Sashas Photo Studio": "SPS",
    "TranceFlow": "TFL",
    "TateKing": "TKG",
    "Fabulousa": "FAB",
    "Imaginarium": "IMG",
    # Development (Code)
    "The Digital Grid": "DGR",
    "The Lab": "LAB",
    "The Workshop": "WRK",
    "The Chaos Party": "TCP",
    # Commercial / Financial
    "The Artifactory": "ART",
    "API Marketplace": "APM",
    "Royal Bank of Arcadia": "RBA",
    "Arcadian Exchange": "AEX",
    "Warp Radio": "WRA",
    # Knowledge
    "The Observatory": "OBS",
    "The Library": "LIB",
    "The Academy": "ACA",
    "DocUtari": "DOC",
    "The Basement": "BSM",
    "The Spark": "SPK",
    # Security
    "Infinity": "INF",
    "The Void": "VOI",
    "The Lighthouse": "LTH",
    "The Warp Tunnel": "WTP",
    "Cryptex": "CRX",
    "The Ice Box": "ICB",
    # DevOps
    "The Dutchy": "DUT",
    "The Citadel": "CTL",
    "Think Tank": "TNK",
    "Turing's Hub": "THB",
    "ChronosSphere / ArcStream": "CHR",
    "DevOcity": "DEV",
    # Wellbeing
    "Tranquility": "TRQ",
    "I-Mind": "IMD",
    "tAimra": "TMR",
    "VRAR3D": "VR3",
    "Resonate": "RES",
}

PILLAR_ABBREVS: Dict[str, str] = {
    "Architectural": "ARCH",
    "Commercial / Financial": "COMM",
    "Creativity": "CREA",
    "Development (Code)": "DEVL",
    "Knowledge": "KNWL",
    "Security": "SECU",
    "DevOps": "DVOP",
    "Wellbeing": "WELL",
}

PRIME_ABBREVS: Dict[str, str] = {
    "Cornelius MacIntyre": "COR",
    "Dorris Fontaine": "DOR",
    "The Guardian": "GRD",
    "The Doctor (Nikolai O'denhim)": "DOC",
    "Voxx": "VOX",
    "Norman Hawkins": "NOR",
    "Savania": "SAV",
    "Trancendos": "TRN",
}


def _assign_ids() -> None:
    """Assign PID, AID, SID, and NID fields to all entities in PLATFORM_ENTITIES.

    Called once at module import time. Overwrites empty string defaults.
    """
    for loc_name, entity in PLATFORM_ENTITIES.items():
        abbrev = LOCATION_ABBREVS.get(loc_name)
        if not abbrev:
            continue  # skip if abbreviation not defined

        # Location PID
        entity.pid = f"PID-{abbrev}"

        # Lead AI AID (Tier 3)
        entity.aid = f"AID-{abbrev}-01"

        # Agent SIDs (Tier 4)
        entity.agent_alpha.sid = f"SID-{abbrev}-01"
        entity.agent_beta.sid = f"SID-{abbrev}-02"

        # Bot NIDs (Tier 5)
        entity.bot_01.nid = f"NID-{abbrev}-01"
        entity.bot_02.nid = f"NID-{abbrev}-02"
        entity.bot_03.nid = f"NID-{abbrev}-03"
        entity.bot_04.nid = f"NID-{abbrev}-04"


# Auto-assign IDs on import
_assign_ids()


def get_entity_by_pid(pid: str) -> Optional[LocationEntity]:
    """Look up a LocationEntity by its PID-XXX identifier."""
    for entity in PLATFORM_ENTITIES.values():
        if entity.pid == pid:
            return entity
    return None


def get_entity_by_aid(aid: str) -> Optional[LocationEntity]:
    """Look up a LocationEntity by its Lead AI AID-XXX-NN identifier."""
    for entity in PLATFORM_ENTITIES.values():
        if entity.aid == aid:
            return entity
    return None


def get_all_ids() -> List[Dict]:
    """Return a flat list of all entity IDs across the platform."""
    result = []
    for loc_name, entity in PLATFORM_ENTITIES.items():
        result.append(
            {
                "id": entity.pid,
                "tier": "Location",
                "name": loc_name,
                "pillar": entity.pillar.value,
            }
        )
        result.append(
            {
                "id": entity.aid,
                "tier": 3,
                "name": entity.lead_ai,
                "location": loc_name,
            }
        )
        result.append(
            {
                "id": entity.agent_alpha.sid,
                "tier": 4,
                "name": entity.agent_alpha.code_name,
                "location": loc_name,
                "role": "Alpha",
            }
        )
        result.append(
            {
                "id": entity.agent_beta.sid,
                "tier": 4,
                "name": entity.agent_beta.code_name,
                "location": loc_name,
                "role": "Beta",
            }
        )
        for bot_field, slot in [
            ("bot_01", "01"),
            ("bot_02", "02"),
            ("bot_03", "03"),
            ("bot_04", "04"),
        ]:
            bot = getattr(entity, bot_field)
            result.append(
                {
                    "id": bot.nid,
                    "tier": 5,
                    "name": bot.code_name,
                    "location": loc_name,
                    "slot": slot,
                }
            )
    return result
