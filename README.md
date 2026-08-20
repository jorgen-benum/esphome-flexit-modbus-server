# ESPHome Flexit Modbus Server

This project implements a Modbus server for Flexit ventilation systems using ESPHome.
**No Flexit CI66 adapter is required.**
> **Note:** This is a work in progress and does not yet support all Flexit CS60 sensors or switches.

> This is a fork of [MSkjel/esphome-flexit-modbus-server](https://github.com/MSkjel/esphome-flexit-modbus-server), the original implementation of the Flexit Modbus server component. This fork builds on that work to add the temporary-profile executor described below (safety-leased mode overrides for humidity boost, fireplace, etc.). If you don't need that, the [original repo](https://github.com/MSkjel/esphome-flexit-modbus-server) may suit you better.

---

## Features

- Control Flexit ventilation systems (tested on CS60, may work with others compatible with CI600 panel)
- Works with ESP8266 or ESP32 microcontrollers
- Integrates with ESPHome for easy Home Assistant support
- No CI66 needed
- Temporary-profile executor: safety-leased, ownership-tracked temporary mode overrides (see below)

---

## Requirements

- Flexit ventilation system with CS60 (or similar) controller
- ESP8266 or ESP32 device
- UART-to-RS485 transceiver (e.g., MAX485, MAX1348)
- Basic ESPHome YAML configuration knowledge

---

## Recommended Hardware

| MCU             | RS485 Breakout Board | Notes                                                                 |
|-----------------|---------------------|-----------------------------------------------------------------------|
| XIAO-ESP32-C3   | XIAO-RS485-Expansion-Board  | [Details](hardware/xiao-esp32-c3-rs485-breakout-board-for-seeed-studio-xiao-tp8485e.md) |

---

## Limitations

- **Supply Air Temperature:** Can only be set if no CI600 is connected (CS60 limitation).
- **Startup Order:** ESP must be powered on before CS60, or CS60 won't poll it.
- **Optimistic Settings:** Some settings are "optimistic" and may not reflect changes from other panels or servers.
- **Address:** Address 1 is required for Heater On/Off to function, but this wont work if you have a CI600 connected.

---

## Quick Start

1. **Connect Hardware:**
   Wire your ESP device to the RS485 transceiver and connect to the Flexit controller.

2. **ESPHome Configuration:**
   Add the following to your ESPHome YAML file (adjust pins and options as needed):

   ```yaml
   wifi:
     fast_connect: true           # Needed if powered from the CS60

   logger:
     baud_rate: 115200
     hardware_uart: UART1
     level: WARN

   external_components:
     - source: github://jorgen-benum/esphome-flexit-modbus-server@main
       refresh: 60s
       components: 
         - flexit_modbus_server

   uart:
     id: modbus_uart
     tx_pin: GPIO1                # Set according to your hardware
     rx_pin: GPIO3                # Set according to your hardware
     baud_rate: 115200

   flexit_modbus_server:
     - id: server
       uart_id: modbus_uart
       address: 3 # Address 1 is required for heater on/off, but this wont work in conjuction with a CI600
       # Depending on hardware/optional:
       # tx_enable_pin: GPIO16    # Set according to your hardware.
       # tx_enable_direct: true   # Set according to your hardware. Inverts the DE signal
   ```

3. **Add Controls, Sensors and the Temporary Profile Executor:**
   [full_config.yaml](full_config.yaml) is the complete reference configuration this fork runs in production: sensors, switches, numbers, buttons, and the temporary-profile executor described below. Copy the pieces you need from it, or use it as a starting point directly.

---

## Temporary Profile Executor

Native Flexit controls (panel, kitchen I/O, manual Stop/Min/Normal/Max) stay authoritative for everyday operation. On top of that, the ESPHome config exposes a generic mechanism for higher-level automations — such as a Home Assistant integration handling humidity boost or fireplace mode — to request a **temporary, safety-leased** mode override without needing to know about each other.

The executor itself is policy-free: it doesn't know what "humidity" or "fireplace" mean. It just applies a requested profile, tracks who owns it, and guarantees it can never get stuck overriding the system if the requester disappears.

### Actions

Two ESPHome user-defined actions (exposed to Home Assistant under the `esphome` domain):

- `apply_temporary_profile(owner, target_mode, supply, extract, lease_seconds)` — request a temporary supply/extract profile at `target_mode` (`Min`, `Normal`, or `Max`), owned by `owner` (an opaque string), for up to `lease_seconds`.
- `release_temporary_profile(owner)` — release the temporary profile, but only if `owner` still matches the current owner.

An identical request (same owner, target mode, supply and extract) only **renews the lease** — it does not rewrite Modbus values or reassert the mode. A different owner or a different profile on the same target replaces the active request while keeping the original restore snapshot. Changing target mode while a lease is active is rejected to avoid mixing snapshots.

### Ownership and safety lease

- On first apply, the executor snapshots the supply/extract values of the overridden profile so it can restore them later.
- Ownership (`Temporary Profile Owner`) and the remaining lease (`Temporary Profile Lease Remaining`) are exposed back to Home Assistant as diagnostic entities.
- Ownership is volatile (`restore_value: no`) — after an ESP reboot the executor never re-claims an existing mode/profile. This is intentionally conservative.
- If the lease expires without renewal, the executor returns to Normal, restores the overridden profile's snapshot, and clears ownership. A caller that wants to keep a temporary profile active must renew the lease before it expires.

### Stop protection

- Temporary requests cannot target Stop.
- New temporary requests are rejected while Flexit is stopped.
- Entering Stop cancels ownership and restores the overridden snapshot, but the executor never commands a mode change away from Stop — only native Flexit controls do that.

### Native takeover

If the panel, kitchen I/O, or another native source changes the running mode away from the owned target, the executor cancels the lease, clears ownership, restores the overridden profile's snapshot, and — unless the takeover left the system in Stop — reasserts Normal mode (skipped if it's already there). All temporary profiles are expected to run from Normal, so returning to Normal on any interruption, not just a clean release, avoids getting stranded in whatever mode a transient native override (e.g. kitchen boost) happens to leave behind. Stop is never touched this way — only native Flexit controls change or leave Stop, and a direct Stop selection during a lease is always honored immediately, no reassertion.

**Known, accepted tradeoff:** a direct Max→Min selection through the ESPHome `Set Mode` select while a lease is active gets caught by this same logic and reasserted back to Normal — the executor has no way to tell a deliberate manual selection apart from a transient native override like kitchen boost, since both look identical on the wire (mode reads Min, nothing else). This is left as-is rather than adding heuristics to guess intent: the reassertion is visible and self-correcting (select Min again and it sticks, since ownership is already cleared by then), and building in a guess would risk silently failing to correct a real kitchen-boost episode in the other direction — worse than a one-time flash-and-retry. Avoid manually switching straight to Min while a lease owns Max; release the lease first, or expect the one-time revert.

Ownership is deliberately generic (any caller can pick an owner string like `humidity` or `fireplace`) so a higher-level controller can implement its own request/ownership/completion policy — including priority between competing requests — without changes to this executor.

---

## Optional extras

<details>
<summary>TCP Bridge</summary>
The TCP bridge feature allows you to monitor the Modbus communication over a TCP connection. This is useful for finding new registers.

### How It Works

When enabled, the TCP bridge creates a server that:
- Accepts TCP connections on the configured port (default: 502)
- Mirrors all UART data to connected clients in real-time (both TX and RX)
- Sends data with directional framing so you can distinguish between sent and received frames

### Frame Protocol

Data is sent to TCP clients using a simple 3-byte header + payload format:
```
[Direction (1 byte)][Length High (1 byte)][Length Low (1 byte)][Payload (N bytes)]
```
- **Direction**: `'T'` (0x54) for TX (ESP→UART), `'R'` (0x52) for RX (UART→ESP)
- **Length**: 16-bit big-endian payload length

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `tcp_bridge_enabled` | boolean | `false` | Enable/disable TCP bridge |
| `tcp_bridge_port` | integer | `502` | TCP port to listen on |
| `tcp_bridge_max_clients` | integer | `4` | Maximum concurrent clients (1-10) |

### Example Configuration

```yaml
flexit_modbus_server:
  - id: server
    uart_id: modbus_uart
    address: 3
    tcp_bridge_enabled: true
    tcp_bridge_port: 8502
    tcp_bridge_max_clients: 2
```

### Monitoring Tool

A Python script for monitoring and decoding the TCP bridge traffic is included in [scripts/tcp_bridge_monitor.py](scripts/tcp_bridge_monitor.py).

**Features:**
- Decodes Modbus RTU frames
- Color-coded TX (ESP→UART) and RX (UART→ESP) traffic
- Track coil state changes with `--coil-changes` flag

</details>

---

## Site-specific notes (this installation)

Observed on the HM43/CS60 unit this fork's `full_config.yaml` is actually flashed to — not confirmed on other models.

**Kitchen boost reports Min mode but drives fan speed from the Max registers.** When the kitchen extraction input activates, the mode reports as `Min`, but the actual fan speed comes from whatever is currently in `Supply/Extract Air Percentage Max`, not Min. This was found by comparing before/after adding the temporary-profile executor: the old fireplace-only implementation always force-restored Max on any takeover, so kitchen boost always saw the commissioned 100%. The executor's original "don't restore on takeover" behavior left a fireplace session's overridden Max value (e.g. 80%) stuck in the register, silently reused by every later kitchen boost. That's why every takeover branch restores the profile snapshot — see "Native takeover" above.

**Kitchen boost also isn't a persistent native mode change — it reverts on its own.** Once kitchen boost ends, the unit falls back to whatever mode was still commanded underneath it, not Normal. If a takeover left ownership cleared without also returning to Normal, the system would end up stuck in Max (or whatever the lease's target was) with nothing left tracking it. That's why non-Stop takeovers reassert Normal mode as well, not just the snapshot (see "Native takeover" above, including the accepted tradeoff that decision comes with). This is considered safe on this unit's panel specifically, since it can only reach Min from Max by passing through Normal first — so reasserting Normal never fights a genuine physical mode change here, only the transient one kitchen boost leaves behind.

---

## TODO

- Add support for more sensors and switches

## License

MIT License

---

## Credits

- Forked from [MSkjel/esphome-flexit-modbus-server](https://github.com/MSkjel/esphome-flexit-modbus-server) — this repo is based on that original implementation.
- [esphome-modbus-server](https://github.com/epiclabs-uc/esphome-modbus-server)
- [modbus-esp8266](https://github.com/emelianov/modbus-esp8266)
