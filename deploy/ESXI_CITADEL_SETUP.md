# The Citadel on VMware ESXi — guest VM provisioning and bootstrap

The other local-mode documents (`docs/architecture/infrastructure-modes.md`) describe a
TrueNAS + GEEKOM mini-PC estate. This one covers the hardware actually in use: a single
**VMware ESXi host**. It is the missing step between "the server is powered on" and
`deploy/LIVE_DEPLOY.md`, which assumes it is talking to a Linux host that already has
Docker.

> **ESXi does not run Docker.** It is a type-1 hypervisor — it runs *virtual machines*.
> Nothing in `docker-compose.production.yml` can run on the ESXi host itself. The Citadel
> runs inside a Linux guest VM on that host. Everything below is about creating and
> preparing that guest.

## 0. Before anything — check thermals

A fan running hard on an otherwise idle host is worth resolving before you put a
sustained workload on it, not after. In the ESXi host client:

- **Monitor → Hardware → System sensors** — read the actual temperatures and fan RPM
  rather than going by ear. ESXi surfaces IPMI/board sensors here when the hardware
  exposes them.
- **Monitor → Performance → CPU** — if CPU is near idle and the fan is still at full
  tilt, this is a hardware/firmware matter (dust, failed bearing, a fan curve stuck at
  100% after a BIOS reset, or a failed temperature sensor), not a load problem.
- Check the host's BIOS/BMC fan policy. Many boards default to full-speed when they
  cannot read a sensor, or after a CMOS reset.

Do not size the VM to the host's full capacity while a cooling fault is unresolved — a
thermally throttled host under a 20-container workload will behave like a slow,
intermittently failing one, and that is a miserable thing to debug on top of a first
deployment.

## 1. Create the guest VM

| Setting | Value | Why |
|---|---|---|
| Guest OS | Ubuntu Server 24.04 LTS (or Debian 12) | Docker's `apt` repositories target these directly; the deploy scripts assume a systemd Linux with bash. |
| vCPU | 4 minimum, 8 preferred | The `core` profile runs ~21 containers. Builds are the spiky part, not steady state. |
| RAM | **16 GB minimum for `core`** | Traefik/Valkey/Vault are small; Prometheus, Grafana and especially **Ollama** are not. Ollama alone wants several GB with a model loaded. 8 GB will boot but will thrash once Ollama pulls a model. |
| Disk | 200 GB thin-provisioned | Container images dominate. The full image set is large; SQLite volumes and Prometheus retention grow steadily after that. |
| Disk mode | Thin provision | Lets you over-commit now and grow, rather than committing the whole 200 GB up front. |
| Network | Bridged to the LAN (not NAT) | The host needs a stable, routable address for Traefik and for DNS to point at later. |
| Firmware | EFI, Secure Boot **off** | Secure Boot complicates third-party kernel modules; nothing here needs it on. |

Enable **VMware Tools** in the guest (`open-vm-tools`) so ESXi can report the guest IP,
quiesce the filesystem for snapshots, and shut it down cleanly.

**Take an ESXi snapshot once the OS is installed and updated, before installing
anything else.** It is the cheapest possible rollback for a first deployment, and you
will want it.

## 2. Give the guest a static address

Traefik terminates TLS for `trancendos.com` and DNS will eventually point at this
machine. A DHCP lease that moves breaks both. Set a static IPv4 address in the guest (or
a DHCP reservation on the router, which is easier to change later).

Note the ESXi host client showed an IPv6 **link-local** address (`fe80::…`). Link-local
addresses are not routable off the local segment — they are fine for reaching the ESXi
web UI from the same LAN, but they cannot be what services bind to or what DNS resolves
to. Use the guest's routable IPv4 (or a global IPv6) for everything below.

## 3. Prepare the guest

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git python3 python3-pip open-vm-tools

# Docker Engine + Compose v2 from Docker's own repository (the distro's docker.io
# package ships an older Compose that the deploy scripts do not target).
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker "$USER"   # log out and back in for this to take effect
docker compose version            # must report v2.x
```

## 4. Get the repository onto the guest

```bash
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3
git submodule update --init --recursive
```

If work exists that has not reached GitHub yet, apply it from a bundle instead of
waiting on the remote:

```bash
git fetch /path/to/<branch>.bundle <branch-name>
git checkout <branch-name>
```

## 5. Deploy

Follow `deploy/LIVE_DEPLOY.md` from here — the guest now satisfies its prerequisites.
Start with the `core` profile and only widen once it is healthy:

```bash
./scripts/deploy_live.sh                      # core — ~21 services
DEPLOY_PROFILE=full ./scripts/deploy_live.sh  # adds 6 more
```

**Do not run `docker compose up` against the whole file.** `docker-compose.production.yml`
defines 173 services with almost no memory limits set; bringing them all up at once on a
single host will exhaust RAM. The staged profiles in `deploy_live.sh` exist precisely to
avoid that, and are the supported path.

Before widening past `full`, add services in small batches and watch `docker stats` — the
compose file's lack of per-service memory limits means one misbehaving worker can starve
the rest rather than being killed on its own.

## 6. Snapshot discipline

Take an ESXi snapshot at each of these points, and delete the older ones once the next
is proven:

1. Clean OS, updated (§1)
2. Docker installed, repo cloned, before first deploy (§3–4)
3. `core` profile healthy (§5)

Snapshots are not backups — they live on the same host and same disks. Once there is
real data in the SQLite volumes, `scripts/dr_restore.py` and the ZFS/backup tooling in
`scripts/` are the actual recovery path.

## Known gaps in this document

- **Not yet validated end to end on real hardware.** Every step above follows from the
  repo's own prerequisites and standard ESXi/Docker practice, but no one has run it on
  this host yet. Treat the RAM and disk figures as starting estimates to be corrected by
  the first real deployment, not as measured requirements.
- **No resource limits.** Only 3 of 173 compose services declare a memory limit. Adding
  them per service is worth doing before running much beyond the `core` profile.
- **Single host, no redundancy.** Everything here puts the whole estate on one physical
  machine with one power supply and, currently, one questionable fan.
