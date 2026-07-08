
A second, standalone output path for this project — instead of an Arduino GIGA R1 +
Display Shield, the radar feed is displayed and sonified on a Clockwork Pi uConsole
(or any Linux machine with Wi-Fi and audio output).

<img width="914" height="1449" alt="image0" src="https://github.com/user-attachments/assets/03a46720-a32d-4d95-b291-ce5e7e8bc09f" />


## Safety & disclaimer

----------------------------------------------------------------------------------------------
This is a hobby project, shared as-is for anyone who wants to build their own version.
A few things to know before you do:

- **LiPo batteries**: incorrect wiring, reverse polarity, or physical damage to a
  LiPo cell can cause fire. Double-check polarity yourself before powering anything
  on, use a charging module rated for the cell you're using, and never leave a
  charging LiPo unattended.
- **RF hardware**: the RD-03D and any radio modules in this project operate
  according to their respective regulatory approvals (e.g. CE) for their intended
  region — verify this applies to your location before use.
- **No warranty**: this repository (firmware, wiring diagrams, enclosures, scripts,
  and this README) is provided without any warranty, express or implied. Verify
  every connection yourself before applying power — don't assume the diagrams or
  code here are free of mistakes.
- **Use at your own risk**: building and operating this project is entirely your
  own responsibility. The author assumes no liability for damage, injury, or loss
  resulting from building or using this project.

If you spot an error in the docs, wiring, or code, please open an issue — corrections
are welcome.
----------------------------------------------------------------------------------------------

## Architecture

```
RD-03D  --UART-->  XIAO ESP32-S3  --Wi-Fi (AP + UDP broadcast)-->  uConsole (Pygame)
```

The XIAO ESP32-S3 hosts its own Wi-Fi access point instead of joining one — no
external router, no fixed IP configuration. It reads the radar over UART exactly as
in the GIGA build, clusters targets within 1m of each other into a single point, and
broadcasts the merged data over UDP. Any device connected to the AP automatically
receives the stream.

| | Value |
|---|---|
| SSID | `RadarNet` |
| Password | `radar12345` |
| Mode | XIAO hosts the AP (not a client) |
| UDP port | 4210 |
| Destination | broadcast (`192.168.4.255`) |

## Hardware

Same RD-03D wiring as the standalone single-sensor build:

| RD-03D | XIAO ESP32-S3 |
|---|---|
| TX | D0 (GPIO1, UART1 RX) |
| RX | D1 (GPIO2, UART1 TX) |
| VCC | 5V |
| GND | GND |

<img width="738" height="594" alt="Transmitter build" src="https://github.com/user-attachments/assets/651c39b9-d1e9-4499-87b4-0992acb2ea30" />


## Bill of materials (transmitter)
| Qty | Part |
|---|---|
| 1 | Seeed Studio XIAO ESP32-S3 |
| 1 | RD-03D radar module (Ai-Thinker) |
| 1 | Toggle switch |
| 1 | MT3608 step-up converter, set to 5V |
| 1 | TP4056 usbc charging module
| 1 | 3.7V LiPo battery (capacity to taste — smaller if the node needs to stay compact) |
| — | Wires, enclosure, glue/tape as needed |

## Receiver (uConsole)

A Python script (`uconsole_radar_receiver.py`) connects to the XIAO's access point
and handles visualization and audio:

**Requirements**

```bash
pip install pygame numpy --break-system-packages
```

**Run**

1. Connect to the `RadarNet` Wi-Fi network
2. `python3 uconsole_radar_receiver.py`

Launches fullscreen automatically (resolution auto-detected). Press `ESC` to quit.

## Features

- **Fullscreen radar display** — sector view, range rings, target dots, a range
  readout at the base of the scope, a small target list, and a mute toggle
- **Real audio synthesis** — sonar-style pings (sharp attack, exponential decay,
  layered harmonics) generated on the fly with NumPy, instead of the buzzer's
  square-wave tones. Ping rate and pitch scale with distance to the closest target
- **Continuous sonar sweep** — a visual arc runs across the sector in sync with the
  audio pings, both on target approach and idling in the background when no target
  is present
- **Smoothed target motion** — positions are interpolated between radar updates so
  targets glide instead of stepping
- **Connection-loss handling** — targets clear automatically if the UDP stream drops
  out, rather than freezing on the last known position


