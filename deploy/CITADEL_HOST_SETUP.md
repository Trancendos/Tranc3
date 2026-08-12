# The Citadel — bare-metal host setup (Dell PowerEdge T610 → Proxmox VE)

Supersedes `deploy/ESXI_CITADEL_SETUP.md`, which assumed the host would stay on VMware.
It will not — see §2 for why. This is the document to follow.

**Target hardware (measured 2026-08-12, from the ESXi host client):**

| | |
|---|---|
| Model | Dell PowerEdge T610 (11th gen, ~2009) |
| CPU | 12 × Intel Xeon X5675 @ 3.07 GHz (Westmere-EP) |
| RAM | 47.98 GB |
| Storage | **0 B — no datastore visible** (see §1) |
| Hostname | `esxi.imb.lan` |
| Address | `192.168.1.4` static (v4), plus SLAAC IPv6 |
| Was running | ESXi 6.7.0 U3, install date 2019-03-31 |

## 1. Blockers to clear before installing anything

Both of these are physical and must be resolved at the machine. Nothing below §1 can
proceed until §1.1 is answered.

### 1.1 No datastore — 13 VMs showing "Invalid"

The host client reported `STORAGE — FREE: 0 B, CAPACITY: 0 B` with zero datastores, and
all 13 inherited VMs listed as **Invalid** with Unknown guest OS and 0 MB. Those VMs are
not individually corrupt: ESXi cannot see the datastore holding them.

`Disk Drive Bay 1 Drive 0` reports **RED** in system sensors, which points at the RAID
virtual disk being offline rather than at ESXi.

**Do this first:** reboot and enter the PERC controller BIOS (**Ctrl+R** at the prompt).
Read the virtual disk state:

| State | Meaning | Action |
|---|---|---|
| Optimal | Array is fine; the datastore problem is elsewhere | Investigate ESXi-side before wiping |
| Degraded | Array is running on reduced redundancy | Replace the failed drive; it will rebuild |
| Failed | Too many members lost | Array is gone — rebuild from scratch |
| Foreign | Controller sees a config it did not create | Import it *only* if the old data matters |

Since the plan is a clean install, a failed array is not a disaster — but you must know
which drives are actually healthy before committing the machine to a rebuild. Do not
build on a disk that is about to die.

### 1.2 Power supply 2 failed — and it is the likely fan cause

`Power Supply 2 Status 0` reports **RED with 38 SEL entries**. That is a persistent
logged fault, not a transient.

**This is very likely why the fans are loud.** Dell PowerEdge firmware ramps chassis fans
when a hardware fault is unresolved — a failed PSU, a failed drive, or an unreadable
sensor. This host has two red faults simultaneously. Dust and failing bearings are the
usual suspects for fan noise, but here there is a much more specific explanation already
in the logs.

Check in this order:
1. Is PSU 2 physically seated, plugged in, and its switch on? A T610 runs on one PSU but
   logs and revs until the fault clears.
2. Reseat it. If it stays red on a known-good outlet and cable, the PSU has failed.
3. Clear the System Event Log once the fault is genuinely resolved — a stale SEL entry
   can keep the fans up on its own.

Running on a single PSU is survivable; you simply have no redundancy. Decide knowingly
rather than by default.

**Also check the remaining fan sensors.** Only `FAN 4` was visible (1,920 RPM, green) in
the screenshot — that reading is *not* high. Scroll the 54-sensor list for FAN 1/2/3/5:
if only one fan is elevated it is a fan fault; if all are, it is the chassis-wide ramp
described above.

## 2. Why not ESXi

The original plan was a Linux guest on the existing ESXi. That is no longer the
recommendation, for reasons specific to this hardware:

- **ESXi 6.7 reached end of general support in October 2022.** It receives no security
  patches.
- **It cannot be upgraded on this CPU.** vSphere 7.0 dropped support for the Xeon 5600
  (Westmere) series outright. The `allowLegacyCPU=true` boot workaround exists but is
  unsupported and known to break patching — not a foundation for a platform meant to
  hold audit logs and secrets.
- **The layer buys little here.** The estate needs one Linux Docker host. Putting an
  unpatchable hypervisor underneath a single VM adds attack surface and complexity for
  no isolation benefit that matters at this scale.
- **Nothing is being preserved.** With the datastore gone, the usual argument for
  leaving a working hypervisor alone does not apply. This is the cheapest possible
  moment to change the decision.

**Chosen replacement: Proxmox VE, bare metal** (owner decision, 2026-08-12). It is free
and open-source, actively maintained, imposes no CPU-generation restriction of the kind
that strands ESXi here, and keeps VMs, snapshots and backups — plus LXC containers — with
a web UI conceptually close to what you already know.

Current release is **Proxmox VE 9.2** (May 2026), built on Debian 13 "Trixie". Take the
latest 9.x ISO.

## 3. Install Proxmox VE

1. **Sort storage first (§1.1).** Create a clean RAID virtual disk in the PERC BIOS from
   drives confirmed healthy.
   - *Note on RAID:* Proxmox documentation prefers ZFS on a plain HBA over hardware
     RAID, because ZFS wants direct disk access for checksumming and self-healing. The
     PERC H700 in a T610 does not do a clean IT-mode passthrough, so the practical
     choice here is: let the PERC present one RAID virtual disk, and install Proxmox on
     it using **LVM-thin or ext4 — not ZFS**. Running ZFS on top of hardware RAID gets
     you ZFS's overhead without its protection.
2. Write the Proxmox VE 9.x ISO to USB, boot the T610 from it.
3. During install: set the hostname, and give it the **static IPv4 `192.168.1.4`** the
   host already uses (or a fresh reserved address — just make it static; DNS will point
   here later and Traefik will terminate TLS on it).
4. After first boot, the web UI is on `https://<ip>:8006`.
5. Proxmox nags about the enterprise repository without a subscription. Switch to the
   **no-subscription** repository — it is the supported free channel, not a crack.

## 4. Create the Citadel guest VM

Do **not** install Docker on the Proxmox host itself. Keep the hypervisor clean; run the
stack in a guest so it can be snapshotted and rebuilt independently.

| Setting | Value | Reasoning |
|---|---|---|
| Guest OS | Ubuntu Server 24.04 LTS | Docker's apt repo targets it directly; deploy scripts assume systemd + bash |
| vCPU | 8 | Of 12 available; leaves the host headroom. Builds are the spiky part |
| RAM | 32 GB | Of 48 GB. Ollama with a model loaded is the biggest single consumer; Prometheus and Grafana are next |
| Disk | 200 GB | Container images dominate; SQLite volumes and Prometheus retention grow after |
| Network | `virtio`, bridged to the LAN | Best throughput; needs a routable address |
| Disk bus | `virtio-scsi`, **discard on** | Lets the guest return freed blocks to thin storage |
| QEMU guest agent | Enabled (install `qemu-guest-agent`) | Clean shutdown, IP reporting, quiesced snapshots |

**Snapshot after the OS is installed and updated, before anything else.** Cheapest
rollback you will ever get, and you will want it on a first deployment.

## 5. Prepare the guest

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git python3 python3-pip qemu-guest-agent

# Docker Engine + Compose v2 from Docker's own repository — the distro's docker.io
# package ships an older Compose than the deploy scripts target.
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker "$USER"   # log out and back in
docker compose version            # must report v2.x
```

## 6. Get the repository onto the guest

```bash
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3
git submodule update --init --recursive
```

For work that has not reached GitHub yet, apply a bundle rather than waiting on the
remote:

```bash
git fetch /path/to/tranc3-work.bundle claude/topology-map
git checkout claude/topology-map
```

## 7. Deploy — staged, never all at once

Follow `deploy/LIVE_DEPLOY.md`. Start narrow:

```bash
./scripts/deploy_live.sh                      # core — ~21 services
DEPLOY_PROFILE=full ./scripts/deploy_live.sh  # adds 6 more
```

**Never run `docker compose up` against the whole file.**
`docker-compose.production.yml` defines **173 services with memory limits on only 3 of
them**. Bringing them all up will exhaust 32 GB and start the OOM killer on whatever it
reaches first. The staged profiles exist precisely to prevent that and are the supported
path.

Add services beyond `full` in small batches, watching `docker stats` between each. The
missing per-service memory limits mean one misbehaving worker can starve the rest
instead of being killed on its own — adding those limits is worthwhile work before
widening much.

## 8. Then: The Workshop (Forgejo)

Once `core` is healthy, standing up Forgejo on this host is the highest-value next step.
`CLAUDE.md` already names Forgejo as the platform's primary CI/CD system with GitHub
Actions as a narrow exception. Running it here makes the GitHub dependency optional
rather than load-bearing — which is what the zero-cost, sovereignty-first architecture
was aiming at, and it removes an entire class of external blocker.

Setup lives in `deploy/forgejo/` (`setup.sh`, `runner-setup.sh`).

## Known gaps

- **Not yet validated on this hardware.** Every step follows from the repo's own
  prerequisites plus standard Proxmox/Docker practice, but nobody has run it on this
  machine. The RAM and disk figures are starting estimates to be corrected by the first
  real deployment.
- **Single host, no redundancy** — one chassis, currently one working PSU, and a RAID
  array of unknown health. Snapshots live on the same disks and are not backups.
- **Hardware is 2009-era.** The Westmere Xeons are why ESXi stranded this box; they will
  eventually strand other software too. Fine for now; not a decade-long foundation.

## Sources

- [vSphere 7.0 unsupported CPUs and ESXi 7.0 hardware requirements — 4sysops](https://4sysops.com/archives/vsphere-7-0-unsupported-cpus-and-esxi-7-0-hardware-requirements/)
- [Quick Tip: Allow unsupported CPUs when upgrading to ESXi 7.0 — William Lam](https://williamlam.com/2020/04/quick-tip-allow-unsupported-cpus-when-upgrading-to-esxi-7-0.html)
- [Proxmox Virtual Environment 9.2 available — Proxmox forum](https://forum.proxmox.com/threads/proxmox-virtual-environment-9-2-available.183742/)
- [Proxmox VE 9.0 with Debian 13 released — Proxmox](https://www.proxmox.com/en/about/company-details/press-releases/proxmox-virtual-environment-9-0)
