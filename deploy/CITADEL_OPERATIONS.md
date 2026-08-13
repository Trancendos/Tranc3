# The Citadel — operations, diagnosis, maintenance and hardening

Companion to `CITADEL_HOST_SETUP.md` (host build) and `CLOUDFLARE_TUNNEL_ACCESS.md`
(internet exposure). This one covers running the box: what to instrument, what to fix,
what to check, and what will bite later.

Hardware in scope: **Dell PowerEdge T610**, 12 × Xeon X5675, 48 GB RAM, PERC RAID,
redundant PSU (one currently failed).

## 1. Dual-boot: ESXi *and* Proxmox on separate drives

Yes — and it is a genuinely good idea here, because it removes the risk from the whole
migration decision.

**Only one hypervisor runs at a time.** This is dual-boot, not side-by-side. You pick at
power-on (**F11** for the Dell boot menu).

### Why this de-risks everything

The uncomfortable part of the migration plan was its one-way nature: wipe ESXi, and if
Proxmox misbehaves on 2009 hardware, you have nothing. Dual-boot removes that:

- ESXi stays intact and bootable as a rollback
- Proxmox gets built and tested at leisure on its own disks
- Migration happens when *you* are satisfied, not under pressure
- If Proxmox turns out to be wrong for this box, you boot back and lose nothing

### Layout

The T610 has 6–8 hot-swap bays plus an **internal USB port** and (usually) an **internal
SD module**. ESXi is designed to boot from those — it runs from a small boot device and
keeps VMs on the datastore.

Recommended split:

| Component | Location |
|---|---|
| ESXi 6.7 boot | Internal SD or USB (move it there if it currently lives on a disk) |
| ESXi datastore | Its existing PERC virtual disk |
| Proxmox boot + storage | A **separate** PERC virtual disk on different physical drives |

Moving ESXi's boot to SD/USB frees a bay and cleanly separates the two systems.

### ⚠️ The one real danger

**Both hypervisors see the same PERC controller and all its virtual disks.** ESXi will
not touch a non-VMFS volume, and Proxmox will not touch VMFS — but the *installer* will
happily reformat whatever you point it at.

- Create Proxmox's virtual disk **first**, in the PERC BIOS, before booting the installer
- At the Proxmox "target disk" step, **read the size and model carefully** and confirm
  you are selecting the new VD, not the one holding your friend's VMs
- If in doubt, physically remove the ESXi datastore drives during the Proxmox install.
  Crude, but it makes the mistake impossible.

That single step is the difference between a safe dual-boot and an accidental wipe of
the thing this whole exercise is trying to preserve.

## 2. iDRAC — the biggest operational win available, and it's already in the box

The T610 ships with **iDRAC6**. Nothing so far has mentioned it, and it is the single
largest improvement to diagnosis, support and remediation on this list.

iDRAC is an independent management processor with its own NIC. It runs whether or not
the OS is up, and gives you:

- **Remote console** — see the BIOS/POST/boot screens from your desk. The PERC `Ctrl+R`
  check does not require standing at the machine.
- **Remote power** — on, off, hard reset, from a browser
- **Hardware health and the SEL** — the same PSU/drive faults, without ESXi
- **Virtual media** (iDRAC6 *Enterprise*) — mount an ISO remotely, so you can install
  Proxmox without a USB stick or physical access
- **IPMI** — which is what makes §3 possible

**Set this up before anything else.** Every subsequent step gets easier, and a server
you can only fix by walking to it is a server that stays broken longer.

Configure it at boot (**Ctrl+E** during POST) with a static IP on your LAN.

> **Security, and this is not optional:** iDRAC6 is from 2009 and has known
> vulnerabilities, including trivially exploitable ones in old firmware. It must **never**
> be internet-facing, must never be tunnelled, and should ideally sit on a management
> VLAN. Update its firmware to the last Dell release. Treat reaching it as requiring VPN
> or physical LAN presence.

## 3. The fan noise — a real fix exists for this generation

Dell firmware ramps fans when it sees an unresolved fault or hardware it does not
recognise. With a **failed PSU** and a **failed drive** both logged, that is the most
likely cause — so fix those first and clear the SEL.

If it persists, 11th-gen PowerEdge supports manual fan control over IPMI, and there is a
[gist of the exact commands for the T610](https://gist.github.com/slykar/f90ad596b18d5ab1eb1c66b2ccf51c54):

```bash
# Switch fan control from automatic to manual
ipmitool -I lanplus -H <idrac-ip> -U root -P <pass> raw 0x30 0x30 0x01 0x00

# Set a static speed — last byte is percent in hex (0x0A = 10%, 0x1E = 30%)
ipmitool -I lanplus -H <idrac-ip> -U root -P <pass> raw 0x30 0x30 0x02 0xff 0x1E

# Hand control back to the firmware
ipmitool -I lanplus -H <idrac-ip> -U root -P <pass> raw 0x30 0x30 0x01 0x01
```

**Understand what this does before using it.** It disables thermal protection. A fixed
low speed under sustained load can cook the CPUs. It reverts to automatic on an iDRAC
reset, which is a safety net but also means it does not survive reboots.

The sane pattern is a small daemon that reads inlet temperature and steps the fan
percentage accordingly, rather than a fixed value —
[R710-Fan-Control](https://github.com/spacelama/R710-Fan-Control) does exactly this and
covers the same generation. Only reach for it once the two red faults are cleared and
the fans are *still* wrong.

## 4. Fold the hardware into The Observatory

The platform already runs Prometheus and Grafana. The host they run on is currently
unmonitored — so a failing PSU or a disk about to go produces no alert in the system
built to watch everything else. Closing that loop is high value and low effort.

| Exporter | Gives you |
|---|---|
| `node_exporter` | CPU, memory, disk, filesystem, load on the Linux guest |
| `ipmi_exporter` | **PSU status, fan RPM, inlet/CPU temps, chassis intrusion — straight from iDRAC** |
| `smartctl_exporter` | Per-disk SMART: reallocated sectors, pending sectors, wear |
| Proxmox PVE exporter | Guest states, host storage, cluster health (if Proxmox) |

`ipmi_exporter` is the one that matters most here. It turns "the fan sounds wrong" into
a Grafana panel and an alert threshold. Both of your current red faults would have
raised an alert weeks before you noticed by ear.

Add alert rules for: PSU redundancy lost, any drive predictive-failure, inlet temp above
threshold, array degraded, filesystem above 85%.

**This is genuinely satisfying architecture:** The Observatory monitoring the metal it
runs on.

## 5. Power — you currently have none in reserve

With PSU 2 failed you are on a single supply, and there is no UPS mentioned.

- **Replace PSU 2.** T610 (11th-gen) PSUs are plentiful and cheap secondhand. Restoring
  redundancy is probably the highest resilience-per-pound available on this machine.
- **Add a UPS.** A T610 pulls meaningful power; size for a clean shutdown, not for
  riding out long outages.
- **Wire it up with NUT** (Network UPS Tools) so the host shuts down gracefully on
  battery rather than dropping dead. An unclean shutdown with SQLite volumes and a Vault
  in flight is how you get corruption.

## 6. Backups — and snapshots are not backups

Snapshots live on the same disks as the thing they protect. A controller or array
failure takes both.

- **Proxmox Backup Server** is free, deduplicating, and integrates natively. It can run
  on a separate cheap box or NAS.
- Follow 3-2-1 as far as budget allows: the platform will hold audit logs, secrets and
  compliance evidence.
- The repo already has `scripts/dr_restore.py` and ZFS snapshot/replication tooling —
  worth wiring to whatever storage you land on.
- **Test a restore.** An untested backup is a hypothesis.

## 7. Security hardening

Beyond the tunnel/Access design in `CLOUDFLARE_TUNNEL_ACCESS.md`:

**Immediate, from what the host already reported:**
- **Expired certificate** — the host client is warning about it. Replace or regenerate.
- **SSH enabled on ESXi** — the host client flags this too. It should be off unless
  actively in use; enable, use, disable.

**On the Linux guest:**
- `unattended-upgrades` for security patches — the whole point of leaving 6.7 behind is
  getting patches, so actually apply them
- SSH: keys only, no password auth, no root login
- `fail2ban` or CrowdSec on anything that does authenticate
- UFW/nftables default-deny inbound — belt and braces behind the tunnel
- Docker: no `--privileged` unless genuinely required, and never expose the daemon socket

**Platform-level (already in the repo):**
- Vault must be sealed at rest and never internet-reachable
- `AUDIT_SIGNING_KEY` set in production (currently flagged as missing in the readiness
  scorecard)
- Pre-commit hooks already run gitleaks/detect-secrets — keep them enforced

**Management plane:**
- iDRAC on a management VLAN, never tunnelled
- Proxmox `:8006` LAN/VPN only
- Consider Tailscale or WireGuard for remote admin rather than exposing anything

## 8. Maintenance rhythm

| Cadence | Task |
|---|---|
| Continuous | Prometheus alerts on PSU, disks, temps, disk space |
| Weekly | Check SEL for new entries; confirm backups ran |
| Monthly | Apply guest security updates; review Access logs |
| Quarterly | **Test a restore**; check SMART trends; dust the chassis |
| Annually | Review firmware (BIOS/PERC/iDRAC); re-evaluate whether the hardware still fits |

**Physical dust matters more than people expect** on a machine of this age. It is a
genuine cause of thermal ramp, and a T610 that has sat in a home lab for years will have
accumulated plenty.

## 9. Honest limits

- **This hardware is 2009-era.** Westmere already stranded it on ESXi; other software
  will follow eventually. Fine now, not a decade-long foundation.
- **One chassis, one point of failure.** No amount of configuration makes a single host
  highly available. Backups off the box are what actually protect you.
- **iDRAC6 is old and not hardenable to modern standards.** Network isolation is the
  control, not patching.
- **None of this is validated on the machine yet.** Commands and settings follow from
  standard practice and Dell documentation for this generation; the first real run will
  correct details.

## Sources

- [Fan control IPMI commands for Dell T610 — GitHub gist](https://gist.github.com/slykar/f90ad596b18d5ab1eb1c66b2ccf51c54)
- [R710-Fan-Control — a fan control daemon for Dell PowerEdge servers](https://github.com/spacelama/R710-Fan-Control)
- [Quiet Fans on Dell PowerEdge Servers Via IPMI](https://blog.hessindustria.com/quiet-fans-on-dell-poweredge-servers-via-ipmi/)
