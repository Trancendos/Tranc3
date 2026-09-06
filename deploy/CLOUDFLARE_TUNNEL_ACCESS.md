# Internet exposure — Cloudflare Tunnel + Access

How The Citadel gets published to the internet without opening a single inbound port,
and how internal services get real per-user authentication without each application
implementing its own.

**Status:** design, not yet built. Nothing here is configured on the host.

## 1. Why a tunnel, not port forwarding

`cloudflared` runs on the host and makes **outbound-only** connections to Cloudflare's
edge. There is no listening port on the WAN, no port-forward on the router, no firewall
hole. An internet-wide scanner has nothing to find.

That distinction is not academic for this estate. The [ESXiArgs campaign compromised
~2,000 hosts in a weekend](https://www.bleepingcomputer.com/news/security/massive-esxiargs-ransomware-attack-targets-vmware-esxi-servers-worldwide/)
by scanning for an exposed hypervisor port and exploiting an unpatched service behind it;
[~18,500 vulnerable internet-facing ESXi servers](https://www.rapid7.com/blog/post/2023/02/06/ransomware-campaign-compromising-vmware-esxi-servers/)
were found the same way. Every attack in that class begins with "the scanner found an
open port". A tunnel removes that first step entirely.

This does **not** make an unpatched host safe — it removes one (very large) attack path,
not all of them. It is a reason to tunnel, not a reason to stay on an EOL hypervisor.

### On the "avoid Cloudflare" policy

`CLAUDE.md` says to avoid Cloudflare Workers where possible, because of rate limits that
bite under sustained use. **Tunnel and Access are different products** with different
limits: Tunnel is free and not metered per-request for this kind of use, and Access is
free up to 50 users. The Workers policy is about compute quotas and should not be read
as "avoid Cloudflare entirely" — the reasoning behind it does not transfer.

## 2. Architecture — one ingress, not many

The instinct is to give every service its own tunnel ingress rule. Don't. Traefik is
already in the stack doing hostname/path routing, TLS, rate limiting and middleware.
Putting cloudflared in front of Traefik means all of that keeps working unchanged.

```
Internet
   │
   ▼
Cloudflare edge  ── TLS terminated here, WAF, Access policies
   │
   │  (outbound-only tunnel — no inbound ports on the host)
   ▼
cloudflared  (container in the compose stack)
   │
   ▼
Traefik :80  ── existing Host()/PathPrefix() rules, middlewares, stripprefix
   │
   ├── tranc3-backend :8000
   ├── cranbania (The Town Hall) :8071
   ├── forgejo (The Workshop) :3456
   └── … every other routed service
```

Adding a service later means adding a Traefik label, exactly as today. The tunnel config
does not change.

### TLS gotcha

Cloudflare terminates TLS at the edge, so the hop from `cloudflared` to Traefik is
inside the Docker network. Point it at Traefik's **HTTP** entrypoint (`http://traefik:80`)
and let Cloudflare own the public certificate.

If you instead point at `https://traefik:443`, Traefik will serve its Let's Encrypt cert
— but Let's Encrypt cannot complete an HTTP-01 challenge when nothing is reachable
inbound, so that cert will fail to issue or renew. Either use DNS-01 for Traefik's certs,
or (simpler) let Cloudflare handle public TLS and keep the internal hop plain HTTP on a
private Docker network.

## 3. What gets published — and what must never

This is the part that matters most. **The management plane never goes through the
tunnel.**

### Published (via the tunnel)

| Hostname | Routes to | Access policy |
|---|---|---|
| `trancendos.com` | Traefik → Arcadia frontend | Public |
| `api.trancendos.com` | Traefik → tranc3-backend / gateway | Public (app auth) |
| `trancendos.com/townhall` | Traefik → cranbania | **Access required** |
| `trancendos.com/the-workshop` | Traefik → Forgejo | **Access required** |

### Never published — LAN or VPN only

- **Proxmox web UI (`:8006`)** and its SSH
- **Host SSH (`:22`)**
- **Vault (`:8200`)** — the secret store must never be internet-reachable, tunnel or not
- **Traefik dashboard**
- **Prometheus (`:9090`)** — Grafana may be published behind Access; Prometheus itself
  has no auth at all
- **The Docker socket**, obviously

Reach these over the LAN, or over a WireGuard/Tailscale link if remote admin is needed.
A tunnel is for publishing *applications*, not for remote administration.

## 4. Cloudflare Access — and retiring the Town Hall IP allowlist

Access sits at Cloudflare's edge and requires identity (email OTP, Google, GitHub, …)
before a request ever reaches the tunnel. The application behind it needs no auth code of
its own.

This directly supersedes a workaround already in the repo. On 2026-08-12 The Town Hall's
ungated read routes were put behind a Traefik `ipallowlist` middleware
(`TOWNHALL_ALLOWED_CIDRS`, see `docker-compose.production.yml`) because CranBania's
browser dashboard has no session layer to carry a credential on reads — gating reads in
its middleware would break the UI.

**Access solves the actual problem rather than working around it:**

| | IP allowlist (current) | Cloudflare Access |
|---|---|---|
| Identifies | An address | A person |
| Off-network use | Breaks | Works |
| Shared/changing IP | Grants everyone on it | Unaffected |
| Audit trail | None | Per-user login log |
| App changes needed | None | None |

**Migration, once Access is live and verified for `/townhall`:** remove the
`townhall-allowlist` middleware from the cranbania router labels and drop
`TOWNHALL_ALLOWED_CIDRS`. Do it in that order — verify Access first, then remove the
allowlist — so there is never a window where reads are ungated.

Keep the `CRANBANIA_API_KEY` fail-closed check regardless. Access protects the network
path; the API key protects mutating routes if anything ever reaches the service another
way. Defence in depth, not either/or.

## 5. Where cloudflared runs

Run it as a container in `docker-compose.production.yml`, on the same Docker network as
Traefik. Sketch:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: tranc3-cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      # Token from the Cloudflare dashboard when the tunnel is created.
      # Treat as a secret — it authorises the tunnel. Vault-sourced like the rest.
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN:?required}
    depends_on:
      - traefik
    networks:
      - tranc3-net
```

Notes:
- `:?required` matches the fail-closed convention already used for `CRANBANIA_API_KEY`
  and `INTERNAL_SECRET` — compose refuses to start rather than running a tunnel with no
  token.
- Ingress rules are configured **dashboard-side** for a token-based tunnel. A single
  public hostname → `http://traefik:80` is all that is needed; Traefik does the rest.
- `cloudflared` needs no published ports. It dials out.

## 6. Order of work

1. Host rebuilt and `core` profile healthy on the LAN (see `CITADEL_HOST_SETUP.md`)
2. Cloudflare account holds the `trancendos.com` zone
3. Create the tunnel, add the `cloudflared` service, verify `trancendos.com` resolves
   through it
4. Add Access policies for `/townhall` and `/the-workshop`
5. Verify Access blocks an unauthenticated request
6. **Only then** remove the Town Hall IP allowlist (§4)

## Open questions

- **Was the ESXi host ever exposed to the internet?** If inbound ports have been open at
  any point in its life, treat the inherited VMs as potentially compromised: migrate
  *data*, rebuild the *machines*. This is worth establishing before anything from the old
  estate is carried onto the new host.
- **Which identity provider for Access?** Email OTP needs no setup and is fine to start.
  GitHub/Google SSO is nicer if there will be more than one operator.
- **Does anything need a static egress IP?** Tunnel changes how outbound traffic is seen
  by third parties in some configurations; if any integration allowlists an origin IP,
  check it before cutover.

## Sources

- [Massive ESXiArgs ransomware attack targets VMware ESXi servers worldwide — BleepingComputer](https://www.bleepingcomputer.com/news/security/massive-esxiargs-ransomware-attack-targets-vmware-esxi-servers-worldwide/)
- [Ransomware Campaign Compromising VMware ESXi Servers — Rapid7](https://www.rapid7.com/blog/post/2023/02/06/ransomware-campaign-compromising-vmware-esxi-servers/)
