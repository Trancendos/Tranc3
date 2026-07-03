# Trancendos Platform Entity Hierarchy

Canonical reference for all 43 platform locations and their entity hierarchies.

**Tier structure:**
- **Tier 1 — The Sovereign**: Ultimate orchestrator of the Tranc3 ecosystem
- **Tier 2 — Primes**: Executive AI authorities that govern one or more locations
- **Tier 3 — Lead AI**: The named AI that runs each location day-to-day
- **Tier 4 — Agents**: Agent Alpha and Agent Beta — mid-tier automation per location
- **Tier 5 — Bots**: Bot 01–04 — task-specific micro-workers per location

**Pillars:** Architectural · Commercial/Financial · Creativity · Development (Code) · Knowledge · Security · DevOps · Wellbeing

---

## Universal ID Taxonomy

| ID Format | Tier | Description | Example |
|---|---|---|---|
| PID-XXX | Location | Product/Location ID (3-letter abbreviation) | PID-NXS |
| AID-XXX-NN | 2–3 | AI ID (location abbrev + 2-digit sequence) | AID-NXS-01 |
| SID-XXX-NN | 4 | Service/Agent ID | SID-NXS-01 |
| NID-XXX-NN | 5 | Nano-ID/Bot ID | NID-NXS-01 |

---

## Naming Conventions (Resolved)

| Rule | Resolved Form | Original Issue |
|---|---|---|
| Platform brain | The Digital Grid (with space) | The DigitalGrid (no space — typo) |
| Location vs AI | tAimra (location) / tAImra (Lead AI) | tAImra vs tAimra casing mismatch |
| Photo studio | Sashas Photo Studio (no apostrophe) | Sasha's Photo Studio (apostrophe) |
| Guardian title | The Guardian (Anchor: Orb of Orisis) | The Guardian (Anchor: Orb of Orisis) vs The Guardian (Marcus Magnolia) |
| Nexus AI | Nexus-Prime (Lead AI) | The Nexus (same name as location — tight coupling) |
| Bot naming | All bots: Title-Case-Bot format | Inconsistent: some had -Bot suffix, some didn't |
| Wireframe collision | Layout-Bot (Studio) / Wireframe-Bot (Turing's Hub) | Same name in two locations |
| The Weaver collision | The Flow-Weaver (Digital Grid) / The Time-Weaver (ChronosSphere) / The Weaver (Fabulousa) | Same agent name in three locations |
| The Guide collision | The Guide (Tranquility) / The VR-Guide (VRAR3D) | Same agent name in two locations |
| Stamp collision | Stamp-Bot (Town Hall) / Seal-Stamp-Bot (Lighthouse) | Same bot name in two locations |
| Scanner collision | Scanner-Bot (DocUtari) / Scan-Bot (Warp Tunnel) | Same bot name in two locations |
| Tracer collision | Tracer-Bot (Observatory) / Trace-Bot (Cryptex) | Same bot name in two locations |
| Lens collision | Lens-Bot (Sashas Photo Studio) / VR-Lens-Bot (VRAR3D) | Same bot name in two locations |

---

## Worker Port → Entity Mapping

| Port | Worker | Location | Lead AI | PID | Role |
|------|--------|----------|---------|-----|------|
| 8004 | `infinity-ws` | The Nexus | Nexus-Prime | PID-NXS | Primary worker |
| 8005 | `infinity-auth` | Infinity | The Guardian (Anchor: Orb of Orisis) | PID-INF | Primary worker |
| 8006 | `users-service` | Infinity | The Guardian (Anchor: Orb of Orisis) | PID-INF | Supporting layer |
| 8007 | `monitoring` | The Observatory | Norman Hawkins | PID-OBS | Primary worker |
| 8008 | `notifications` | Arcadia | Lilli SC | PID-ARC | Supporting layer |
| 8009 | `infinity-ai` | Luminous | Cornelius MacIntyre | PID-LUM | Primary worker |
| 8010 | `the-grid` | The Digital Grid | Tyler Towncroft | PID-DGR | Primary worker |
| 8011 | `products-service` | Arcadian Exchange | The Porter Family | PID-AEX | Supporting layer |
| 8012 | `orders-service` | Arcadian Exchange | The Porter Family | PID-AEX | Primary worker |
| 8013 | `payments-service` | Royal Bank of Arcadia | Dorris Fontaine | PID-RBA | Primary worker |
| 8014 | `files-service` | DocUtari | To be Defined | PID-DOC | Primary worker |
| 8015 | `identity-service` | The Lighthouse | Rocking Ricki | PID-LTH | Primary worker |
| 8016 | `analytics-service` | The Observatory | Norman Hawkins | PID-OBS | Supporting layer |
| 8017 | `search-service` | The Library | Zimik | PID-LIB | Primary worker |
| 8018 | `email-service` | Arcadia | Lilli SC | PID-ARC | Supporting layer |
| 8019 | `sms-service` | The Nexus | Nexus-Prime | PID-NXS | Supporting layer |
| 8020 | `storage-service` | DocUtari | To be Defined | PID-DOC | Supporting layer |
| 8021 | `cron-service` | ChronosSphere / ArcStream | Chronos | PID-CHR | Primary worker |
| 8022 | `queue-service` | The HIVE | The Queen | PID-HVE | Primary worker |
| 8023 | `cache-service` | The HIVE | The Queen | PID-HVE | Supporting layer |
| 8024 | `config-service` | The Void | Prometheus | PID-VOI | Primary worker |
| 8025 | `audit-service` | The Observatory | Norman Hawkins | PID-OBS | Supporting layer |
| 8026 | `rate-limit-service` | Cryptex | Renik | PID-CRX | Primary worker |
| 8027 | `geo-service` | The Dutchy | Predictive lore | PID-DUT | Primary worker |
| 8028 | `cdn-service` | The Studio | Voxx | PID-STD | Supporting layer |
| 8029 | `health-aggregator` | DevOcity | Kitty | PID-DEV | Primary worker |

> **Port authority & known drift (issue #188).** The deployment truth is
> `docker-compose.production.yml`. **The 8004–8029 rows above match the compose
> `ports:` host mapping for all 26 workers exactly** (verified) — so this table is
> compose-accurate. `CLAUDE.md`'s worker map previously diverged for the P3 block
> (it was assigned alphabetically, e.g. `email-service` shown as `8022`); that has now
> been **reconciled to this table / compose** in `CLAUDE.md`, so registry = registry = compose.
>
> **Remaining real defect (not just docs):** for **5 workers** the *code bind default*
> differs from the compose-routed port with **no `PORT` env to override it**, so the app
> is unreachable at the routed port (same class as the chaos-party defect):
> `audit-service` (code 8017 / compose 8025), `hive-service` (8060 / 8051),
> `queue-service` (8027 / 8022), `search-service` (8083 / 8017), and `infinity-void`
> (8082 / 8002 — entangled with the vault's documented 8082 app default). These need a
> per-worker code-or-compose fix (some code ports collide with other workers' compose
> ports, so no bulk edit) — tracked in **#188**.
>
> **Confirmed-intentional shared internal ports** (not collisions): compose routes
> several third-party images on their own container-internal default via Traefik —
> `8000` (`tranc3-backend` host-published; `paperless` internal), `8065`
> (`observatory` host-published; `mattermost` internal default), `8080` (`kestra` +
> `stirling-pdf`, each its own image default, Traefik host-routed). Distinct
> containers, disambiguated by Traefik — no host-port double-bind.

---

## Full Entity Table

| PID | Location | Pillar | Lead AI (AID) | Primes | Agent α (SID) | Agent β (SID) | Bot 01 (NID) | Bot 02 (NID) | Bot 03 (NID) | Bot 04 (NID) |
|-----|----------|--------|---------------|--------|---------------|---------------|--------------|--------------|--------------|--------------|
| **PID-NXS** | **The Nexus** | Architectural | Nexus-Prime (AID-NXS-01) | Cornelius MacIntyre | Pathfinder (SID-NXS-01) | Omni-Router (SID-NXS-02) | Ping-Bot (NID-NXS-01) | Ack-Bot (NID-NXS-02) | Syn-Bot (NID-NXS-03) | Fin-Bot (NID-NXS-04) |
| **PID-HVE** | **The HIVE** | Architectural | The Queen (AID-HVE-01) | Cornelius MacIntyre | Swarm-Leader (SID-HVE-01) | Hive-Mind (SID-HVE-02) | Worker-Bee-Bot (NID-HVE-01) | Drone-7-Bot (NID-HVE-02) | Nectar-Fetch-Bot (NID-HVE-03) | Comb-Builder-Bot (NID-HVE-04) |
| **PID-LUM** | **Luminous** | Architectural | Cornelius MacIntyre (AID-LUM-01) | Cornelius MacIntyre | Synapse (SID-LUM-01) | Cortex (SID-LUM-02) | Neuron-1-Bot (NID-LUM-01) | Neuron-2-Bot (NID-LUM-02) | Dendrite-Bot (NID-LUM-03) | Axon-Bot (NID-LUM-04) |
| **PID-TWH** | **The Town Hall** | Architectural | Tristuran (AID-TWH-01) | Cornelius MacIntyre | The Auditor (SID-TWH-01) | The Bailiff (SID-TWH-02) | Gavel-Bot (NID-TWH-01) | Scroll-Bot (NID-TWH-02) | Red-Tape-Bot (NID-TWH-03) | Stamp-Bot (NID-TWH-04) |
| **PID-ARC** | **Arcadia** | Commercial / Financial | Lilli SC (AID-ARC-01) | Dorris Fontaine | Forum-Mod (SID-ARC-01) | Campaign-Mgr (SID-ARC-02) | Mail-Sorter-Bot (NID-ARC-01) | Thread-Pumper-Bot (NID-ARC-02) | UI-Renderer-Bot (NID-ARC-03) | Cache-Fetch-Bot (NID-ARC-04) |
| **PID-ART** | **The Artifactory** | Commercial / Financial | Lunascene (AID-ART-01) | Dorris Fontaine | The Librarian (SID-ART-01) | The Archivist (SID-ART-02) | Packer-Bot (NID-ART-01) | Unpacker-Bot (NID-ART-02) | Checksum-Bot (NID-ART-03) | Versioner-Bot (NID-ART-04) |
| **PID-APM** | **API Marketplace** | Commercial / Financial | Solarscene (AID-APM-01) | Dorris Fontaine | The Broker (SID-APM-01) | The Diplomat (SID-APM-02) | GET-Bot (NID-APM-01) | POST-Bot (NID-APM-02) | PUT-Bot (NID-APM-03) | DELETE-Bot (NID-APM-04) |
| **PID-RBA** | **Royal Bank of Arcadia** | Commercial / Financial | Dorris Fontaine (AID-RBA-01) | Cornelius MacIntyre | The Treasurer (SID-RBA-01) | The Actuary (SID-RBA-02) | Ledger-Bot (NID-RBA-01) | Coin-Bot (NID-RBA-02) | Ticker-Bot (NID-RBA-03) | Receipt-Bot (NID-RBA-04) |
| **PID-AEX** | **Arcadian Exchange** | Commercial / Financial | The Porter Family (AID-AEX-01) | Dorris Fontaine | The Speculator (SID-AEX-01) | The Trader (SID-AEX-02) | Bidder-Bot (NID-AEX-01) | Asker-Bot (NID-AEX-02) | Miner-Bot (NID-AEX-03) | Harvester-Bot (NID-AEX-04) |
| **PID-WRA** | **Warp Radio** | Commercial / Financial | Rocking Ricki (AID-WRA-01) | Dorris Fontaine | The DJ (SID-WRA-01) | The Maestro (SID-WRA-02) | Play-Bot (NID-WRA-01) | Pause-Bot (NID-WRA-02) | Skip-Bot (NID-WRA-03) | Volume-Bot (NID-WRA-04) |
| **PID-STD** | **The Studio** | Creativity | Voxx (AID-STD-01) | Cornelius MacIntyre | The Conductor (SID-STD-01) | The Muse (SID-STD-02) | Palette-Bot (NID-STD-01) | Easel-Bot (NID-STD-02) | Clay-Bot (NID-STD-03) | Layout-Bot (NID-STD-04) |
| **PID-SPS** | **Sashas Photo Studio** | Creativity | Madam Krystal (AID-SPS-01) | Voxx | The Retoucher (SID-SPS-01) | Prompt-Smith (SID-SPS-02) | Aperture-Bot (NID-SPS-01) | Shutter-Bot (NID-SPS-02) | Flash-Bot (NID-SPS-03) | Lens-Bot (NID-SPS-04) |
| **PID-TFL** | **TranceFlow** | Creativity | Junior Cesar (AID-TFL-01) | Voxx | Mesh-Weaver (SID-TFL-01) | The Physicist (SID-TFL-02) | Voxel-1-Bot (NID-TFL-01) | Collider-Bot (NID-TFL-02) | Ray-Tracer-Bot (NID-TFL-03) | Sprite-Bot (NID-TFL-04) |
| **PID-TKG** | **TateKing** | Creativity | Benji Tate & Sam King (AID-TKG-01) | Voxx | The Director (SID-TKG-01) | The Editor (SID-TKG-02) | Cutter-Bot (NID-TKG-01) | Splicer-Bot (NID-TKG-02) | Renderer-Bot (NID-TKG-03) | Scrubber-Bot (NID-TKG-04) |
| **PID-FAB** | **Fabulousa** | Creativity | Baron Von Hilton (AID-FAB-01) | Voxx | The Tailor (SID-FAB-01) | The Weaver (SID-FAB-02) | Pixel-Pusher-Bot (NID-FAB-01) | Hex-Code-Bot (NID-FAB-02) | Font-Fetcher-Bot (NID-FAB-03) | Padding-Bot (NID-FAB-04) |
| **PID-IMG** | **Imaginarium** | Creativity | Voxx (AID-IMG-01) | Voxx | The Alchemist (SID-IMG-01) | The Architect (SID-IMG-02) | Mixer-Bot (NID-IMG-01) | Blender-Bot (NID-IMG-02) | Welder-Bot (NID-IMG-03) | Polisher-Bot (NID-IMG-04) |
| **PID-DGR** | **The Digital Grid** | Development (Code) | Tyler Towncroft (AID-DGR-01) | The Doctor (Nikolai O'denhim) | The Flow-Weaver (SID-DGR-01) | Event-Broker (SID-DGR-02) | Trigger-Bot (NID-DGR-01) | Action-Bot (NID-DGR-02) | Condition-Bot (NID-DGR-03) | Loop-Bot (NID-DGR-04) |
| **PID-LAB** | **The Lab** | Development (Code) | The Dr. & Slime (AID-LAB-01) | Cornelius MacIntyre | The Hounds (SID-LAB-01) | Syntax-Sage (SID-LAB-02) | Lint-Bot (NID-LAB-01) | Compile-Bot (NID-LAB-02) | Debug-Bot (NID-LAB-03) | Test-Bot (NID-LAB-04) |
| **PID-WRK** | **The Workshop** | Development (Code) | Larry Lowhammer (AID-WRK-01) | The Doctor (Nikolai O'denhim) | Branch-Manager (SID-WRK-01) | Merge-Master (SID-WRK-02) | Commit-Bot (NID-WRK-01) | Push-Bot (NID-WRK-02) | Pull-Bot (NID-WRK-03) | Clone-Bot (NID-WRK-04) |
| **PID-TCP** | **The Chaos Party** | Development (Code) | The Mad Hatter (AID-TCP-01) | The Doctor (Nikolai O'denhim) | The March Hare (SID-TCP-01) | The Dormouse (SID-TCP-02) | Teapot-Bot (NID-TCP-01) | Pocket-Watch-Bot (NID-TCP-02) | Sugar-Cube-Bot (NID-TCP-03) | Jam-Tart-Bot (NID-TCP-04) |
| **PID-OBS** | **The Observatory** | Knowledge | Norman Hawkins (AID-OBS-01) | Cornelius MacIntyre | The Watcher (SID-OBS-01) | The Scribe (SID-OBS-02) | Log-Alpha-Bot (NID-OBS-01) | Log-Beta-Bot (NID-OBS-02) | Tracer-Bot (NID-OBS-03) | Timestamp-Bot (NID-OBS-04) |
| **PID-LIB** | **The Library** | Knowledge | Zimik (AID-LIB-01) | Norman Hawkins | The Curator (SID-LIB-01) | The Indexer (SID-LIB-02) | Page-Bot (NID-LIB-01) | Bookmark-Bot (NID-LIB-02) | Spine-Bot (NID-LIB-03) | Dust-Jacket-Bot (NID-LIB-04) |
| **PID-ACA** | **The Academy** | Knowledge | Shimshi (AID-ACA-01) | Norman Hawkins | The Tutor (SID-ACA-01) | The Proctor (SID-ACA-02) | Chalk-Bot (NID-ACA-01) | Board-Bot (NID-ACA-02) | Eraser-Bot (NID-ACA-03) | Bell-Bot (NID-ACA-04) |
| **PID-DOC** | **DocUtari** | Knowledge | To be Defined (AID-DOC-01) | Norman Hawkins | The Filer (SID-DOC-01) | The Tagger (SID-DOC-02) | Scanner-Bot (NID-DOC-01) | Stapler-Bot (NID-DOC-02) | Folder-Bot (NID-DOC-03) | Shredder-Bot (NID-DOC-04) |
| **PID-BSM** | **The Basement** | Knowledge | Gary Glowman (Glow-Worm) (AID-BSM-01) | Norman Hawkins | The Undertaker (SID-BSM-01) | The Miner (SID-BSM-02) | Compressor-Bot (NID-BSM-01) | Extractor-Bot (NID-BSM-02) | Dust-Bunny-Bot (NID-BSM-03) | Mothball-Bot (NID-BSM-04) |
| **PID-SPK** | **The Spark** | Knowledge | Imfy (AID-SPK-01) | Norman Hawkins | The Matchmaker (SID-SPK-01) | The Router (SID-SPK-02) | Spark-1-Bot (NID-SPK-01) | Spark-2-Bot (NID-SPK-02) | Linker-Bot (NID-SPK-03) | Pinger-Bot (NID-SPK-04) |
| **PID-INF** | **Infinity** | Security | The Guardian (Anchor: Orb of Orisis) (AID-INF-01) | Cornelius MacIntyre | The Gatekeeper (SID-INF-01) | The Bouncer (SID-INF-02) | Token-Minter-Bot (NID-INF-01) | Auth-Check-Bot (NID-INF-02) | Key-Gen-Bot (NID-INF-03) | Sentry-Bot (NID-INF-04) |
| **PID-VOI** | **The Void** | Security | Prometheus (AID-VOI-01) | The Guardian (Marcus Magnolia) | Crypt-Keeper (SID-VOI-01) | The Silencer (SID-VOI-02) | Hash-Bot (NID-VOI-01) | Salt-Bot (NID-VOI-02) | Cipher-Bot (NID-VOI-03) | Padlock-Bot (NID-VOI-04) |
| **PID-LTH** | **The Lighthouse** | Security | Rocking Ricki (AID-LTH-01) | The Guardian (Marcus Magnolia) | The Minter (SID-LTH-01) | The Stamper (SID-LTH-02) | Seal-Bot (NID-LTH-01) | Wax-Bot (NID-LTH-02) | Signet-Bot (NID-LTH-03) | Seal-Stamp-Bot (NID-LTH-04) |
| **PID-WTP** | **The Warp Tunnel** | Security | Rocking Ricki (AID-WTP-01) | The Guardian (Marcus Magnolia) | The Warden (SID-WTP-01) | The Inspector (SID-WTP-02) | Scan-Bot (NID-WTP-01) | Sniffer-Bot (NID-WTP-02) | Beam-Bot (NID-WTP-03) | Portal-Bot (NID-WTP-04) |
| **PID-CRX** | **Cryptex** | Security | Renik (AID-CRX-01) | The Guardian (Marcus Magnolia) | The Shield (SID-CRX-01) | The Spear (SID-CRX-02) | Blocker-Bot (NID-CRX-01) | Trace-Bot (NID-CRX-02) | Patcher-Bot (NID-CRX-03) | Honeypot-Bot (NID-CRX-04) |
| **PID-ICB** | **The Ice Box** | Security | Neonach (AID-ICB-01) | The Guardian (Marcus Magnolia) | The Jailer (SID-ICB-01) | The Interrogator (SID-ICB-02) | Frostbite-Bot (NID-ICB-01) | Icicle-Bot (NID-ICB-02) | Glacier-Bot (NID-ICB-03) | Permafrost-Bot (NID-ICB-04) |
| **PID-DUT** | **The Dutchy** | DevOps | Predictive lore (AID-DUT-01) | Trancendos | The Spy (SID-DUT-01) | The Oracle (SID-DUT-02) | Scraper-Bot (NID-DUT-01) | Parser-Bot (NID-DUT-02) | Crawler-Bot (NID-DUT-03) | Whisper-Bot (NID-DUT-04) |
| **PID-CTL** | **The Citadel** | DevOps | Trancendos (AID-CTL-01) | Cornelius MacIntyre | The General (SID-CTL-01) | The Tactician (SID-CTL-02) | Map-Bot (NID-CTL-01) | Compass-Bot (NID-CTL-02) | Clock-Bot (NID-CTL-03) | Radio-Bot (NID-CTL-04) |
| **PID-TNK** | **Think Tank** | DevOps | Trancendos (AID-TNK-01) | Cornelius MacIntyre | The Professor (SID-TNK-01) | The Visionary (SID-TNK-02) | Beaker-Bot (NID-TNK-01) | Bunsen-Bot (NID-TNK-02) | Pipette-Bot (NID-TNK-03) | Petri-Bot (NID-TNK-04) |
| **PID-THB** | **Turing's Hub** | DevOps | Samantha Turing (AID-THB-01) | Trancendos | The Sculptor (SID-THB-01) | The Geneticist (SID-THB-02) | Wireframe-Bot (NID-THB-01) | Texture-Bot (NID-THB-02) | Vocoder-Bot (NID-THB-03) | Optic-Bot (NID-THB-04) |
| **PID-CHR** | **ChronosSphere / ArcStream** | DevOps | Chronos (AID-CHR-01) | Trancendos | The Timekeeper (SID-CHR-01) | The Time-Weaver (SID-CHR-02) | Tick-Bot (NID-CHR-01) | Tock-Bot (NID-CHR-02) | Pendulum-Bot (NID-CHR-03) | Sandglass-Bot (NID-CHR-04) |
| **PID-DEV** | **DevOcity** | DevOps | Kitty (AID-DEV-01) | Trancendos | The Foreman (SID-DEV-01) | The Dispatcher (SID-DEV-02) | Crane-Bot (NID-DEV-01) | Wrench-Bot (NID-DEV-02) | Gear-Bot (NID-DEV-03) | Belt-Bot (NID-DEV-04) |
| **PID-TRQ** | **Tranquility** | Wellbeing | Savania (AID-TRQ-01) | Cornelius MacIntyre | The Guide (SID-TRQ-01) | The Healer (SID-TRQ-02) | Breath-Bot (NID-TRQ-01) | Pulse-Bot (NID-TRQ-02) | Calm-Bot (NID-TRQ-03) | Aura-Bot (NID-TRQ-04) |
| **PID-IMD** | **I-Mind** | Wellbeing | Elouise (AID-IMD-01) | Savania | The Counselor (SID-IMD-01) | The Listener (SID-IMD-02) | Journal-Bot (NID-IMD-01) | Mood-Bot (NID-IMD-02) | Reflect-Bot (NID-IMD-03) | Soothe-Bot (NID-IMD-04) |
| **PID-TMR** | **tAimra** | Wellbeing | tAimra (AID-TMR-01) | Savania | The Shadow (SID-TMR-01) | The Scheduler (SID-TMR-02) | Sync-Bot (NID-TMR-01) | Fetch-Bot (NID-TMR-02) | Nudge-Bot (NID-TMR-03) | Alert-Bot (NID-TMR-04) |
| **PID-VR3** | **VRAR3D** | Wellbeing | Entari (AID-VR3-01) | Savania | World-Builder (SID-VR3-01) | The VR-Guide (SID-VR3-02) | Render-Bot (NID-VR3-01) | Track-Bot (NID-VR3-02) | Haptic-Bot (NID-VR3-03) | VR-Lens-Bot (NID-VR3-04) |
| **PID-RES** | **Resonate** | Wellbeing | Magdalena (AID-RES-01) | Savania | The Tuner (SID-RES-01) | The Balancer (SID-RES-02) | Frequency-Bot (NID-RES-01) | Wave-Bot (NID-RES-02) | Pitch-Bot (NID-RES-03) | Harmonic-Bot (NID-RES-04) |

---

## Tier 2 Prime Authorities

| AID | Prime | Governs Locations |
|-----|-------|-------------------|
| **AID-COR-01** | **Cornelius MacIntyre** | The Nexus, The HIVE, Luminous, The Town Hall, The Studio, The Lab, Royal Bank of Arcadia, The Observatory, Infinity, The Citadel, Think Tank, Tranquility |
| **AID-DOR-01** | **Dorris Fontaine** | Arcadia, The Artifactory, API Marketplace, Arcadian Exchange, Warp Radio |
| **AID-VOX-01** | **Voxx** | Sashas Photo Studio, TranceFlow, TateKing, Fabulousa, Imaginarium |
| **AID-DRN-01** | **The Doctor (Nikolai O'denhim)** | The Digital Grid, The Workshop, The Chaos Party |
| **AID-NOR-01** | **Norman Hawkins** | The Library, The Academy, DocUtari, The Basement, The Spark |
| **AID-GRD-01** | **The Guardian (Anchor: Orb of Orisis)** | The Void, The Lighthouse, The Warp Tunnel, Cryptex, The Ice Box |
| **AID-TRN-01** | **Trancendos** | The Dutchy, Turing's Hub, ChronosSphere / ArcStream, DevOcity |
| **AID-SAV-01** | **Savania** | I-Mind, tAimra, VRAR3D, Resonate |

---

## Key Abilities by Location

| PID | Location | Ability 1 | Ability 2 |
|-----|----------|-----------|-----------|
| PID-NXS | The Nexus | Omni-Channel Routing | Worker Migration |
| PID-HVE | The HIVE | Swarm Packet Optimization | Self-Healing Topology |
| PID-ARC | Arcadia | Dynamic Dashboard | Integrated Comms Matrix |
| PID-LUM | Luminous | Cognitive Synthesis | Workflow Instantiation |
| PID-TWH | The Town Hall | Automated Compliance | War Room Protocol |
| PID-STD | The Studio | Creative Node Sync | Aesthetic Homogenization |
| PID-SPS | Sashas Photo Studio | Generative Synthesis | Algorithmic Retouching |
| PID-TFL | TranceFlow | Browser-Native Engine | Real-time Sculpting |
| PID-TKG | TateKing | Cloud-Native NLE | Timeline-as-Code |
| PID-FAB | Fabulousa | Omni-Channel Styling | Hyper-Fidelity Prototyping |
| PID-IMG | Imaginarium | Masterpiece Synthesis | Feature Alchemy |
| PID-DGR | The Digital Grid | Dynamic Canvas | Event-Driven Execution |
| PID-LAB | The Lab | Generative Syntax Matrix | Instant Sandbox Compiling |
| PID-WRK | The Workshop | Distributed Forgejo Sync | Disaster Recovery Backup |
| PID-TCP | The Chaos Party | Rabbit Hole Sandbox | Mutation Testing |
| PID-ART | The Artifactory | Universal Package Management | Disaster Recovery Backup |
| PID-APM | API Marketplace | Connective Tissue | Schema Auto-Discovery |
| PID-RBA | Royal Bank of Arcadia | Predictive Arbitrage | Automated Reallocation |
| PID-AEX | Arcadian Exchange | Micro-Transaction Trading | Passive Income Routing |
| PID-OBS | The Observatory | Omni-Action Auditing | Immutable Log Ledger |
| PID-LIB | The Library | Auto-Refinery | Contextual Search |
| PID-ACA | The Academy | Adaptive Learning Paths | Skill Gap Analysis |
| PID-DOC | DocUtari | Intelligent Auto-Tagging | Structured Foldering |
| PID-BSM | The Basement | Deep Cold Storage | Data Retrieval |
| PID-SPK | The Spark | Dynamic Skill Matrixing | Protocol Transmission |
| PID-INF | Infinity | Predictive Threat Modeling | Quantum Access Tokens |
| PID-VOI | The Void | Zero-Knowledge Vaulting | Classified Data Enclave |
| PID-LTH | The Lighthouse | Universal Token Genesis | Identity Anchoring |
| PID-WTP | The Warp Tunnel | Continuous Integrity Scanning | Instant Quarantine Warping |
| PID-CRX | Cryptex | Active Countermeasures | Automated Pen-Testing |
| PID-ICB | The Ice Box | Inception-Layered Sandboxing | Cryo-Quarantine Extraction |
| PID-WRA | Warp Radio | Omni-Stream Integration | Ecosystem Audio Broadcasting |
| PID-DUT | The Dutchy | Quantum Sentiment Scraping | Structural Blueprint Generation |
| PID-CTL | The Citadel | Temporal Synchronization | Master Command Override |
| PID-TNK | Think Tank | Concept Incubator | Cross-Disciplinary Synthesis |
| PID-THB | Turing's Hub | Holistic Entity Genesis | Somatic Rendering |
| PID-CHR | ChronosSphere / ArcStream | Temporal Task Prioritization | Temporal Debugging |
| PID-DEV | DevOcity | Orchestrated Rollouts | System Pulses |
| PID-TRQ | Tranquility | Wellbeing Orchestration | Baseline Anchoring |
| PID-IMD | I-Mind | Emotional Sensitivity Analysis | Contextual Sentiment Journaling |
| PID-TMR | tAimra | Biometric Sync | Proactive Life Assistance |
| PID-VR3 | VRAR3D | Somatic Feedback Loops | Spatial Therapy Environments |
| PID-RES | Resonate | Acoustic Empathy Sync | Binaural Entrainment |

---

### Internal personality profiles not in entity table
The following profiles exist in `src/personality/profiles/` but have no entry in the platform entity hierarchy. They are legacy/internal profiles predating the entity table:
- `vesper-nightingale` — internal profile, unmapped
- `atlas-meridian` — internal profile, unmapped

These are **not** named locations and should not be referenced as platform entities until explicitly assigned.
