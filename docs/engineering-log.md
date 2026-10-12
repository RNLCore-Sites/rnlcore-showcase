# Engineering log

Real problems I hit building RNLCore on actual hardware, and what I did about them.

## Standby cellular data was costing money for nothing → ~94% lower

**Symptom:** Units sitting on standby, with the ISP healthy, were still burning metered cellular data.
**Cause:** GL.iNet's multi-WAN daemon (`kmwan`) health-checks every interface, including cellular, every 3 seconds.
**Fix:** Retuned the check interval to 35 seconds. Outage detection stays fast enough for a shop, and idle SIM cost dropped by about 94%.

## Service enforcement that can't run up a bill → fail-closed lock

**Problem:** A device that's unpaid, stolen, or cut off from the server must not keep using cellular data.
**Design:** `rnl-checkin` reports to the control plane. If it can't confirm service, `rnl-lock` installs an iptables/ip6tables FORWARD chain that blocks forwarding over cellular. The control plane can also return `wired_only`, so a billing problem removes the backup path without breaking the customer's normal internet.

## Modem hangs → self-healing watchdog

**Problem:** 5G modems occasionally stop responding, which defeats the point of a backup.
**Fix:** A watchdog with an escalation ladder that retries the modem in stages and, if it stays dead after three attempts, raises an alert to the control plane:

```
RNL_CORE: WAN down - modem watchdog activating
RNL_CORE: Heal L4: modem unresponsive after 3 attempts - alerting Control Plane
```

## Latency spiked under load → 316 ms penalty down to 22 ms

**Measured:** ~4.7 Mbps down, 350 ms unloaded and 666 ms loaded latency on the cellular path. That's bad for card terminals and VoIP during an outage.
**After config changes:** ~7.8 Mbps down / 25 Mbps up, 169 ms unloaded / 191 ms loaded. The extra latency under load fell from about 316 ms to about 22 ms.
**Also found:** the carrier's public IP broke out in Oregon for a New Jersey unit, which explains the baseline latency and is a carrier-routing tradeoff to weigh when picking a provider.

## One client couldn't stream video → IPv6 bearer failure

**Symptom:** A single tablet failed to play video on the router's Wi-Fi while every other client was fine.
**Investigation:** Ruled out egress IP blocks by testing other clients on the same network, then read the system log: the SIM rejected IPv6 data calls (QMI error on `requestSetupDataCall`) and the modem retried every 60 seconds.
**Fix:** Run the cellular interface IPv4-only. The IPv4 bearer then dialed cleanly in about 20 seconds with no retry loop.

## Every unit configured by hand → "Golden Base" build kit

**Problem:** Reproducing the patched firmware on each new router was slow and error-prone.
**Fix:** Packaged everything into a staged build: base image, overlay, patched modem script, and network/modem configs, run by `build_golden_base.sh`. Any stock X3000 becomes an RNLCore unit the same way every time.

## Device identity → can't be spoofed by the device

**Problem:** If a router could pick or change its own ID, anyone could clone a paid unit.
**Fix:** IDs are UUIDv4s generated off-device and written once to `/etc/rnl/identity.json`. The server validates the format and only honors IDs an admin registered. Unknown IDs always get a locked policy.
