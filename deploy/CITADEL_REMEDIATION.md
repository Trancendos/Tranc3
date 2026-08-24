# Citadel remediation runbook

Every alert in `monitoring/alerts/citadel-hardware.yml` carries a `runbook`
annotation pointing at a section here. An alert that does not say what to do about
it is a notification, not an alert.

**Hardware in scope:** Dell PowerEdge T610, iDRAC6, PERC RAID, redundant PSU.

## How to use this

1. Alert fires → Alertmanager → the `runbook` annotation names a section below
2. Follow **Assess** before **Act** — several of these have a failure mode where
   the obvious action makes things worse
3. Record what you did; the SEL and Grafana keep the timeline, but not the reasoning

---

## psu-failure

**Alert:** `CitadelPowerSupplyFailed` · severity critical

### Assess
- Which supply? `ipmi_sensor_state{type="Power Supply"}` labels name it
- Is the chassis still up? If yes you are on the surviving supply with no spare
- Check the SEL for when it started — a supply that has been faulted for weeks is
  a different story from one that failed ten minutes ago

### Act
1. **Check the boring causes first.** Is it plugged in, switched on, and is the
   outlet live? A supply that was never energised reports identically to a dead one.
2. Reseat it. Power down first if the chassis has no redundancy left.
3. Try a known-good cable and a different outlet.
4. If it still faults, the supply has failed. T610 (11th-gen) PSUs are common and
   cheap secondhand — replacing it restores redundancy.
5. Once genuinely resolved, **clear the SEL** (see `sel-management`). A stale
   entry keeps the firmware in a degraded posture, including the fan ramp.

### Do not
- Do not ignore it because the server is still running. You are one supply from
  an unplanned outage, and the fans will stay loud until it clears.

---

## unexpected-power-off

**Alert:** `CitadelChassisPowerOff` · severity critical

The BMC answers even when the host does not, so this is a real reading rather
than a scrape failure.

### Assess
- Was it planned? Check recent tasks and your own change record
- SEL will show thermal shutdown, power loss, or a clean ACPI shutdown — these
  are very different causes
- Mains failure? If a UPS is fitted, check whether it ran to empty

### Act
1. Power on via iDRAC (remote — no need to walk to it)
2. Watch POST through the iDRAC console for errors
3. If it was thermal, go to `thermal` before bringing workloads back up
4. If it was power loss and there is no UPS, that is the finding — see
   `CITADEL_OPERATIONS.md` §5

---

## thermal

**Alerts:** `CitadelInletTemperatureHigh` (warn, >35C) · `CitadelInletTemperatureCritical` (crit, >40C)

Dell rates this generation to 35C ambient inlet.

### Assess
- Inlet vs CPU temperature: high **inlet** is a room/airflow problem; normal
  inlet with high **CPU** is a heatsink, fan or load problem
- Is the room hot, or is airflow blocked?
- **Has anyone set fan control to manual?** This is the one that catches people
  — a static low fan speed set for noise will cook the machine under load

### Act
1. **If fan control was set to manual, hand it back immediately:**
   ```bash
   ipmitool -I lanplus -H <idrac-ip> -U <user> -P <pass> raw 0x30 0x30 0x01 0x01
   ```
2. Clear obstructions; confirm intake and exhaust are unblocked
3. Check for dust — significant on a machine of this age, and a real cause
4. If ambient is genuinely high, that is a room problem, not a server one
5. At critical and climbing, shut down gracefully rather than let it throttle
   and eventually trip

---

## fan-failure

**Alert:** `CitadelFanStopped` · severity critical

A fan at 0 RPM with the chassis powered on has failed — these do not idle.

### Assess
- Which fan, and where in the chassis (front intake vs CPU vs PSU)
- Are the remaining fans compensating? They will be louder
- Any thermal alert alongside it?

### Act
1. Order a replacement — T610 fans are a standard part
2. Until it arrives, monitor `thermal` closely; margin is reduced
3. If a thermal alert accompanies it, reduce load or shut down
4. Replace, then clear the SEL

---

## fan-noise

**Alert:** `CitadelFansRunningHot` · severity warning

Sustained high RPM with no thermal alert almost always means the firmware is
compensating for a **fault**, not for heat.

### Assess — in this order
1. **Any asserted hardware fault?** Failed PSU or drive is the usual cause.
   Resolve those first; the fans follow.
2. **Stale SEL entries?** The firmware can hold a degraded posture after the
   underlying fault is fixed. Clear the log.
3. **Non-Dell hardware fitted?** Third-party cards or drives the firmware cannot
   identify make it default to full cooling — a known PowerEdge behaviour.
4. **Actually hot?** Check inlet temperature before assuming otherwise.

### Act
Only once 1–3 are genuinely resolved, consider manual fan control:

```bash
# Manual mode
ipmitool -I lanplus -H <idrac-ip> -U <user> -P <pass> raw 0x30 0x30 0x01 0x00
# Set static speed — last byte is percent in hex (0x1E = 30%)
ipmitool -I lanplus -H <idrac-ip> -U <user> -P <pass> raw 0x30 0x30 0x02 0xff 0x1E
```

> ⚠️ **This disables thermal protection.** A fixed low speed under sustained load
> will overheat the CPUs. It also reverts on iDRAC reset — a useful safety net,
> but it means the setting does not survive a reboot.
>
> A temperature-stepped daemon is the safer pattern than a fixed percentage —
> see [R710-Fan-Control](https://github.com/spacelama/R710-Fan-Control), which
> covers this generation. Prefer it over a static value if you go down this road
> at all.

---

## drive-failure

**Alert:** `CitadelDriveFault` · severity critical

### Assess
- Which bay? The sensor name maps to the physical slot
- **Array state matters more than drive state.** Reboot to the PERC BIOS
  (`Ctrl+R`) or use OMSA/`storcli` if available:
  - **Optimal** — one drive predictive-failing but the array is fine
  - **Degraded** — running without redundancy; a second failure loses data
  - **Failed** — array offline, data inaccessible

### Act
1. **If Degraded: replace the drive promptly.** This is the window where a
   second failure is fatal. Rebuilds are slow on this generation and load the
   surviving disks hardest — the riskiest moment is during the rebuild.
2. **Verify backups before starting a rebuild.** If the rebuild kills another
   disk, backups are what is left.
3. Insert the replacement; the PERC should rebuild automatically. If it does not,
   set it as a hot spare or trigger the rebuild manually.
4. Watch the rebuild to completion.
5. **If Failed:** stop. Do not initialise or import anything until you have
   decided about recovery. Writing to a failed array can destroy what is
   recoverable.

### Do not
- Do not pull a drive to "test" it. On a degraded array that is how you lose it.

---

## sel-management

**Alert:** `CitadelSELFillingUp` · severity warning

A full SEL stops recording — you lose the log exactly when events are frequent
enough to fill it.

### Act
1. **Read it before clearing it.** It is the only record of what happened.
   ```bash
   ipmitool -I lanplus -H <idrac-ip> -U <user> -P <pass> sel list
   ```
2. Resolve what it reports — repeated entries mean an unfixed fault
3. Export or note anything worth keeping
4. Clear:
   ```bash
   ipmitool -I lanplus -H <idrac-ip> -U <user> -P <pass> sel clear
   ```
5. Confirm it stays quiet. Refilling means the fault is still live.

Clearing the SEL after a genuine fix is also what stops the firmware holding a
degraded posture — including the fan ramp in `fan-noise`.

---

## chassis-intrusion

**Alert:** `CitadelChassisIntrusion` · severity warning

### Assess
- Expected? Anyone doing maintenance right now?
- Correlate with physical access to the room

### Act
1. If planned, note it and clear the sensor
2. If **not** planned, treat as a security event: who had access, was anything
   changed, do any other sensors show new hardware
3. Physical access defeats most software controls. If the machine holds secrets
   or audit data, unexplained intrusion warrants rotating credentials.

---

## bmc-unreachable

**Alert:** `CitadelBMCUnreachable` · severity warning

**This one is different: it means monitoring is blind.** While it persists, no
PSU, thermal or drive alert can fire — they all depend on this scrape.

### Assess
- Is the host itself up? BMC down with host up points at the BMC, not the machine
- Reachable by ping? By the iDRAC web UI?
- Did credentials change? Did the iDRAC IP change?

### Act
1. Check the iDRAC network link and address
2. Verify the monitoring user still exists with login privilege
3. **iDRAC6 wedges occasionally** — reset it without touching the host:
   ```bash
   ipmitool -I lanplus -H <idrac-ip> -U <user> -P <pass> mc reset cold
   ```
   Safe while the host runs; iDRAC is independent of it.
4. If it will not come back, `racadm racreset` from the host OS, or reseat power
   entirely (full drain — pull the cords, hold the power button)
5. **While blind, check hardware manually.** Do not assume silence is health.

---

## Escalation

| Condition | Action |
|---|---|
| Array **Failed**, data needed | Stop. Do not write. Consider professional recovery before touching anything |
| Repeated thermal criticals | Take load off; treat as unsafe until cooling is proven |
| Multiple simultaneous faults | Suspect power or backplane rather than coincidence |
| Intrusion + no explanation | Rotate credentials; treat host as untrusted until reviewed |

## Known gaps

- **Not validated on the hardware.** The alert expressions follow ipmi-exporter's
  documented metric names, but sensor naming varies between BMC firmware versions.
  Expect to adjust the `name=~` regexes once real metrics are flowing — check
  what iDRAC6 actually emits at `http://ipmi-exporter:9290/ipmi?target=<idrac-ip>`
  and correct the rules to match.
- **Thresholds are starting points**, not tuned values. 35C/40C follow Dell's
  ambient rating; the 8000 RPM fan threshold is a guess until real baselines exist.
- **No auto-remediation.** Everything here is human-in-the-loop by design.
  Automatically power-cycling a host or clearing a SEL on a fault you have not
  read is how a small problem becomes an outage.
