# Trancendos Platform Entity Hierarchy

Canonical reference for all 43 platform locations and their entity hierarchies.

**Tier structure:**
- **Tier 2 — Primes**: Executive AI authorities that govern one or more locations
- **Tier 3 — Lead AI**: The named AI that runs each location day-to-day
- **Tier 4 — Agents**: Agent Alpha and Agent Beta — mid-tier automation per location
- **Tier 5 — Bots**: Bot 01–04 — task-specific micro-workers per location

**Pillars:** Architectural · Commercial/Financial · Creativity · Development (Code) · Knowledge · Security · DevOps · Wellbeing

---

## Naming Conventions

| Rule | Correct | Incorrect |
|---|---|---|
| Platform brain | The Digital Grid | The DigitalGrid (no space — entity table typo) |
| Location vs AI | tAimra (location) / tAImra (Lead AI) | Using them interchangeably |
| Photo studio | Sashas Photo Studio | Sasha's Photo Studio (no apostrophe in canonical name) |
| Guardian full title | The Guardian (Anchor: Orb of Orisis) | The Guardian (shortened) |

### Internal personality profiles not in entity table
The following profiles exist in `src/personality/profiles/` but have no entry in the platform entity hierarchy. They are legacy/internal profiles predating the entity table:
- `vesper-nightingale` — internal profile, unmapped
- `atlas-meridian` — internal profile, unmapped

These are **not** named locations and should not be referenced as platform entities until explicitly assigned.

---

## Worker Port → Entity Mapping

| Port | Worker | Location | Lead AI | Role |
|------|--------|----------|---------|------|
| 8004 | `infinity-ws` | The Nexus | The Nexus | Primary worker |
| 8005 | `infinity-auth` | Infinity | The Guardian | Primary worker |
| 8006 | `users-service` | Infinity | The Guardian | Supporting layer |
| 8007 | `monitoring` | The Observatory | Norman Hawkins | Primary worker |
| 8008 | `notifications` | Arcadia | Lilli SC | Supporting layer |
| 8009 | `infinity-ai` | Luminous | Cornelius MacIntyre | Primary worker |
| 8010 | `the-grid` | The Digital Grid | Tyler Towncroft | Primary worker |
| 8011 | `products-service` | Arcadian Exchange | The Porter Family | Supporting layer |
| 8012 | `orders-service` | Arcadian Exchange | The Porter Family | Primary worker |
| 8013 | `payments-service` | Royal Bank of Arcadia | Dorris Fontaine | Primary worker |
| 8014 | `files-service` | DocUtari | To be Defined | Primary worker |
| 8015 | `identity-service` | The Lighthouse | Rocking Ricki | Primary worker |
| 8016 | `analytics-service` | The Observatory | Norman Hawkins | Supporting layer |
| 8017 | `search-service` | The Library | Zimik | Primary worker |
| 8018 | `email-service` | Arcadia | Lilli SC | Supporting layer |
| 8019 | `sms-service` | The Nexus | The Nexus | Supporting layer |
| 8020 | `storage-service` | DocUtari | To be Defined | Supporting layer |
| 8021 | `cron-service` | ChronosSphere / ArcStream | Chronos | Primary worker |
| 8022 | `queue-service` | The HIVE | The Queen | Primary worker |
| 8023 | `cache-service` | The HIVE | The Queen | Supporting layer |
| 8024 | `config-service` | The Void | Prometheus | Primary worker |
| 8025 | `audit-service` | The Observatory | Norman Hawkins | Supporting layer |
| 8026 | `rate-limit-service` | Cryptex | Renik | Primary worker |
| 8027 | `geo-service` | The Dutchy | Predictive lore | Primary worker |
| 8028 | `cdn-service` | The Studio | Voxx | Supporting layer |
| 8029 | `health-aggregator` | DevOcity | Kitty | Primary worker |

---

## Full Entity Table

| Location | Pillar | Lead AI (Tier 3) | Primary Function | Primes (Tier 2) | Agent Alpha (Tier 4) | Agent Beta (Tier 4) | Bot 01 (Tier 5) | Bot 02 (Tier 5) | Bot 03 (Tier 5) | Bot 04 (Tier 5) |
|---|---|---|---|---|---|---|---|---|---|---|
| **The Nexus** | Architectural | The Nexus | AI Communication Gateway & Transfer Hub | Cornelius MacIntyre | Pathfinder | Omni-Router | Ping-Bot | Ack-Bot | Syn-Bot | Fin-Bot |
| **The HIVE** | Architectural | The Queen | Data Transport Hub | Cornelius MacIntyre | Swarm-Leader | Hive-Mind | Worker-Bee | Drone-7 | Nectar-Fetch | Comb-Builder |
| **Arcadia** | Commercial / Financial | Lilli SC | Post-Login User Frontend, Forum & Email Hub | Dorris Fontaine | Forum-Mod | Campaign-Mgr | Mail-Sorter | Thread-Pumper | UI-Renderer | Cache-Fetch |
| **Luminous** | Architectural | Cornelius MacIntyre | Core Platform Brain & Orchestration Engine | Cornelius MacIntyre | Synapse | Cortex | Neuron-1 | Neuron-2 | Dendrite | Axon |
| **The Town Hall** | Architectural | Tristuran | Governance & Compliance Center | Cornelius MacIntyre | The Auditor | The Bailiff | Gavel | Scroll | Red-Tape | Stamp |
| **The Studio** | Creativity | Voxx | Central Hub of the Creativity Center | Cornelius MacIntyre | The Conductor | The Muse | Palette | Easel | Clay | Wireframe |
| **Sashas Photo Studio** | Creativity | Madam Krystal | Photo & Image Generation Center | Voxx | The Retoucher | Prompt-Smith | Aperture | Shutter | Flash | Lens |
| **TranceFlow** | Creativity | Junior Cesar | 3D Modeling & Games Creation Studio | Voxx | Mesh-Weaver | The Physicist | Voxel-1 | Collider | Ray-Tracer | Sprite |
| **TateKing** | Creativity | Benji Tate & Sam King | Video Creation & Editing Platform | Voxx | The Director | The Editor | Cutter | Splicer | Renderer | Scrubber |
| **Fabulousa** | Creativity | Baron Von Hilton | Styling, UX, UI & Design Center | Voxx | The Tailor | The Weaver | Pixel-Pusher | Hex-Code | Font-Fetcher | Padding-Bot |
| **Imaginarium** | Creativity | Voxx | Omni-Creative Masterpiece Wizard | Voxx | The Alchemist | The Architect | Mixer | Blender | Welder | Polisher |
| **The Digital Grid** | Development (Code) | Tyler Towncroft | Workflow Platform | The Doctor (Nikolai O'denhim) | The Weaver | Event-Broker | Trigger | Action | Condition | Loop |
| **The Lab** | Development (Code) | The Dr. & Slime | Code Creation Platform | Cornelius MacIntyre | The Hounds | Syntax-Sage | Lint-Bot | Compile-Bot | Debug-Bot | Test-Bot |
| **The Workshop** | Development (Code) | Larry Lowhammer | Repository Storage (Forgejo) | The Doctor (Nikolai O'denhim) | Branch-Manager | Merge-Master | Commit-Bot | Push-Bot | Pull-Bot | Clone-Bot |
| **The Chaos Party** | Development (Code) | The Mad Hatter | Central Testing Platform | The Doctor (Nikolai O'denhim) | The March Hare | The Dormouse | Teapot | Pocket-Watch | Sugar-Cube | Jam-Tart |
| **The Artifactory** | Commercial / Financial | Lunascene | Central Artifact Repository Library | Dorris Fontaine | The Librarian | The Archivist | Packer | Unpacker | Checksum | Versioner |
| **API Marketplace** | Commercial / Financial | Solarscene | Central Integration Hub | Dorris Fontaine | The Broker | The Diplomat | GET-Bot | POST-Bot | PUT-Bot | DELETE-Bot |
| **Royal Bank of Arcadia** | Commercial / Financial | Dorris Fontaine | Financial & Operations Management | Cornelius MacIntyre | The Treasurer | The Actuary | Ledger | Coin | Ticker | Receipt |
| **Arcadian Exchange** | Commercial / Financial | The Porter Family | Procurement & Resource Trading | Dorris Fontaine | The Speculator | The Trader | Bidder | Asker | Miner | Harvester |
| **The Observatory** | Knowledge | Norman Hawkins | Audit Log & Monitoring Platform | Cornelius MacIntyre | The Watcher | The Scribe | Log-Alpha | Log-Beta | Tracer | Timestamp |
| **The Library** | Knowledge | Zimik | Knowledge Base & Wiki | Norman Hawkins | The Curator | The Indexer | Page | Bookmark | Spine | Dust-Jacket |
| **The Academy** | Knowledge | Shimshi | Education & Skill Training | Norman Hawkins | The Tutor | The Proctor | Chalk | Board | Eraser | Bell |
| **DocUtari** | Knowledge | To be Defined | Document Management Hub | Norman Hawkins | The Filer | The Tagger | Scanner | Stapler | Folder | Shredder |
| **The Basement** | Knowledge | Gary Glowman (Glow-Worm) | Archived Information Store | Norman Hawkins | The Undertaker | The Miner | Compressor | Extractor | Dust-Bunny | Mothball |
| **The Spark** | Knowledge | Imfy | The MCP Skills Matrix | Norman Hawkins | The Matchmaker | The Router | Spark-1 | Spark-2 | Linker | Pinger |
| **Infinity** | Security | The Guardian (Anchor: Orb of Orisis) | Centralized Auth & OAuth 2.0 | Cornelius MacIntyre | The Gatekeeper | The Bouncer | Token-Minter | Auth-Check | Key-Gen | Sentry |
| **The Void** | Security | Prometheus | Secrets Vault & Password Store | The Guardian (Marcus Magnolia) | Crypt-Keeper | The Silencer | Hash | Salt | Cipher | Padlock |
| **The Lighthouse** | Security | Rocking Ricki | Cryptographic Token Applicator | The Guardian (Marcus Magnolia) | The Minter | The Stamper | Seal | Wax | Signet | Stamp |
| **The Warp Tunnel** | Security | Rocking Ricki | Cryptographic Scanner & Quarantine Transport | The Guardian (Marcus Magnolia) | The Warden | The Inspector | Scanner | Sniffer | Beam | Portal |
| **Cryptex** | Security | Renik | Cyber Defense (Threat Intel, DDoS, CVE) | The Guardian (Marcus Magnolia) | The Shield | The Spear | Blocker | Tracer | Patcher | Honeypot |
| **The Ice Box** | Security | Neonach | Sandbox Threat Isolation & Quarantine | The Guardian (Marcus Magnolia) | The Jailer | The Interrogator | Frostbite | Icicle | Glacier | Permafrost |
| **Warp Radio** | Commercial / Financial | Rocking Ricki | Music & Audio Streaming Integration | Dorris Fontaine | The DJ | The Maestro | Play | Pause | Skip | Volume |
| **The Dutchy** | DevOps | Predictive lore | Intelligence & Market Analysis | Trancendos | The Spy | The Oracle | Scraper | Parser | Crawler | Whisper |
| **The Citadel** | DevOps | Trancendos | Strategic Ops & DevOps Fortress | Cornelius MacIntyre | The General | The Tactician | Map | Compass | Clock | Radio |
| **Think Tank** | DevOps | Trancendos | R&D Centre | Cornelius MacIntyre | The Professor | The Visionary | Beaker | Bunsen | Pipette | Petri |
| **Turing's Hub** | DevOps | Samantha Turing | Central Entity Creation Forge | Trancendos | The Sculptor | The Geneticist | Wireframe | Texture | Vocoder | Optic |
| **ChronosSphere / ArcStream** | DevOps | Chronos | Task, Time & Scheduling Management | Trancendos | The Timekeeper | The Weaver | Tick | Tock | Pendulum | Sandglass |
| **DevOcity** | DevOps | Kitty | Development Operations | Trancendos | The Foreman | The Dispatcher | Crane | Wrench | Gear | Belt |
| **Tranquility** | Wellbeing | Savania | Wellbeing Central Hub | Cornelius MacIntyre | The Guide | The Healer | Breath | Pulse | Calm | Aura |
| **I-Mind** | Wellbeing | Elouise | Sensitivity to Emotion Engine | Savania | The Counselor | The Listener | Journal | Mood | Reflect | Soothe |
| **tAimra** | Wellbeing | tAImra | Opt-in Digital Twin & Life Assistant | Savania | The Shadow | The Scheduler | Sync | Fetch | Nudge | Alert |
| **VRAR3D** | Wellbeing | Entari | Standalone 3D / VR Immersion | Savania | World-Builder | The Guide | Render | Track | Haptic | Lens |
| **Resonate** | Wellbeing | Magdalena | Empathy Engine | Savania | The Tuner | The Balancer | Frequency | Wave | Pitch | Harmonic |

---

## Tier 2 Prime Authorities

| Prime | Governs Locations |
|---|---|
| **Cornelius MacIntyre** | The Nexus, The HIVE, Luminous, The Town Hall, The Studio, The Digital Grid (indirect), The Lab, Royal Bank of Arcadia, The Observatory, Infinity, The Citadel, Think Tank, Tranquility |
| **Dorris Fontaine** | Arcadia, The Artifactory, API Marketplace, Arcadian Exchange, Warp Radio |
| **The Guardian (Marcus Magnolia)** | The Void, The Lighthouse, The Warp Tunnel, Cryptex, The Ice Box |
| **The Doctor (Nikolai O'denhim)** | The Digital Grid, The Workshop, The Chaos Party |
| **Voxx** | Sashas Photo Studio, TranceFlow, TateKing, Fabulousa, Imaginarium |
| **Norman Hawkins** | The Library, The Academy, DocUtari, The Basement, The Spark |
| **Savania** | I-Mind, tAimra, VRAR3D, Resonate |
| **Trancendos** | The Dutchy, Turing's Hub, ChronosSphere / ArcStream, DevOcity |

---

## Key Abilities by Location

| Location | Ability 1 | Ability 2 |
|---|---|---|
| The Nexus | Omni-Channel Routing | Worker Migration |
| The HIVE | Swarm Packet Optimization | Self-Healing Topology |
| Arcadia | Dynamic Dashboard | Integrated Comms Matrix |
| Luminous | Cognitive Synthesis | Workflow Instantiation |
| The Town Hall | Automated Compliance | War Room Protocol |
| The Studio | Creative Node Sync | Aesthetic Homogenization |
| Sashas Photo Studio | Generative Synthesis | Algorithmic Retouching |
| TranceFlow | Browser-Native Engine | Real-time Sculpting |
| TateKing | Cloud-Native NLE | Timeline-as-Code |
| Fabulousa | Omni-Channel Styling | Hyper-Fidelity Prototyping |
| Imaginarium | Masterpiece Synthesis | Feature Alchemy |
| The Digital Grid | Dynamic Canvas | Event-Driven Execution |
| The Lab | Generative Syntax Matrix | Instant Sandbox Compiling |
| The Workshop | Distributed Forgejo Sync | Disaster Recovery Backup |
| The Chaos Party | Rabbit Hole Sandbox | Mutation Testing |
| The Artifactory | Universal Package Management | Disaster Recovery Backup |
| API Marketplace | Connective Tissue | Schema Auto-Discovery |
| Royal Bank of Arcadia | Predictive Arbitrage | Automated Reallocation |
| Arcadian Exchange | Micro-Transaction Trading | Passive Income Routing |
| The Observatory | Omni-Action Auditing | Immutable Log Ledger |
| The Library | Auto-Refinery | Contextual Search |
| The Academy | Adaptive Learning Paths | Skill Gap Analysis |
| DocUtari | Intelligent Auto-Tagging | Structured Foldering |
| The Basement | Deep Cold Storage | Data Retrieval |
| The Spark | Dynamic Skill Matrixing | Protocol Transmission |
| Infinity | Predictive Threat Modeling | Quantum Access Tokens |
| The Void | Zero-Knowledge Vaulting | Classified Data Enclave |
| The Lighthouse | Universal Token Genesis | Identity Anchoring |
| The Warp Tunnel | Continuous Integrity Scanning | Instant Quarantine Warping |
| Cryptex | Active Countermeasures | Automated Pen-Testing |
| The Ice Box | Inception-Layered Sandboxing | Cryo-Quarantine Extraction |
| Warp Radio | Omni-Stream Integration | Ecosystem Audio Broadcasting |
| The Dutchy | Quantum Sentiment Scraping | Structural Blueprint Generation |
| The Citadel | Temporal Synchronization | Master Command Override |
| Think Tank | Concept Incubator | Cross-Disciplinary Synthesis |
| Turing's Hub | Holistic Entity Genesis | Somatic Rendering |
| ChronosSphere / ArcStream | Temporal Task Prioritization | Temporal Debugging |
| DevOcity | Orchestrated Rollouts | System Pulses |
| Tranquility | Wellbeing Orchestration | Baseline Anchoring |
| I-Mind | Emotional Sensitivity Analysis | Contextual Sentiment Journaling |
| tAimra | Biometric Sync | Proactive Life Assistance |
| VRAR3D | Somatic Feedback Loops | Spatial Therapy Environments |
| Resonate | Acoustic Empathy Sync | Binaural Entrainment |
