# HomeAssistant-Hewalex2MQTT

An [AppDaemon](https://appdaemon.readthedocs.io/) app that bridges a **Hewalex PCWU heat pump** to Home Assistant via MQTT. It reads status and configuration registers over RS485 and publishes them as MQTT topics. It also accepts MQTT command messages to write configuration values back to the device.

Based on the work by [Jojan265](https://gathering.tweakers.net/forum/view_message/79522762) and [Chibald/Hewalex2Mqtt](https://github.com/Chibald/Hewalex2Mqtt).

---

## Table of contents

1. [What it does](#1-what-it-does)
2. [Requirements](#2-requirements)
3. [RS485 hardware options](#3-rs485-hardware-options)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [MQTT topics](#6-mqtt-topics)
7. [Home Assistant integration](#7-home-assistant-integration)
8. [Troubleshooting](#8-troubleshooting)
9. [Credits](#9-credits)

---

## 1. What it does

- Polls the Hewalex PCWU heat pump every **60 seconds** for status registers (temperatures, component states)
- Polls configuration registers every **10 minutes** (target temperature, hysteresis, defrost settings)
- Publishes all values as retained MQTT messages under a configurable base topic (default: `Heatpump`)
- Subscribes to `<topic>/Command/<register>` for write-back commands from Home Assistant
- Exposes a `sensor.hewalex_status` entity in HA (`online` / `offline`) via the watchdog
- Handles RS485 connection errors gracefully with automatic reconnect and a 60 s cooldown

---

## 2. Requirements

**Software**
- Home Assistant with the [AppDaemon add-on](https://github.com/hassio-addons/addon-appdaemon) installed
- An MQTT broker (e.g. Mosquitto add-on)
- Python packages (installed automatically by AppDaemon if listed in its config):
  - `pyserial`
  - `paho-mqtt`

**Hardware**
- A Hewalex PCWU heat pump with the RS485 port accessible
- An RS485-to-TCP or RS485-to-USB adapter (see section 3)

---

## 3. RS485 hardware options

The script connects to the heat pump via a TCP socket (`socket://ip:port`). You need an RS485-to-Ethernet adapter.

| Option | Example | Notes |
|---|---|---|
| RS485-to-Ethernet | Waveshare RS485 TO ETH (B) | Recommended. Configure as TCP server on port 8899. |
| RS485-to-USB + ser2net | Any USB-RS485 dongle | Run `ser2net` on a Pi or server to expose the port over TCP. |
| Direct USB (not recommended) | — | Requires modifying the serial URL in the script; no TCP gateway needed but less flexible. |

The gateway **must** be configured for: 38400 baud, 8 data bits, no parity, 1 stop bit.

---

## 4. Installation

1. **Install the AppDaemon add-on** in Home Assistant (Supervisor → Add-on store → AppDaemon).

2. **Copy the app files** to the AppDaemon apps directory (typically `/addon_configs/a0d7b954_appdaemon/apps/`):
   ```
   hewalex2mqtt.py
   hewalex2mqttconfig.ini        ← create from the .example file
   hewalex_geco/                 ← include the full directory
   ```

3. **Add the app to `apps.yaml`** (in the same apps directory):
   ```yaml
   hewalex2mqtt:
     module: hewalex2mqtt
     class: Hewalex2MQTT
   ```

4. **Create `hewalex2mqttconfig.ini`** by copying `hewalex2mqttconfig.ini.example` and filling in your values (see section 5).

5. **Add the HA package** `config/packages/hewalex.yaml` to your Home Assistant `/config/packages/` directory (see section 7).

6. **Restart AppDaemon**. Check the AppDaemon log for `Starting Hewalex2MQTT` and subsequent `Read OK` lines.

---

## 5. Configuration

All settings are in `hewalex2mqttconfig.ini`. Copy `hewalex2mqttconfig.ini.example` and edit:

### [MQTT]

| Key | Description |
|---|---|
| `MQTT_ip` | IP address of your MQTT broker |
| `MQTT_port` | MQTT port (default: `1883`) |
| `MQTT_authentication` | `True` / `False` — enable broker authentication |
| `MQTT_user` | MQTT username |
| `MQTT_pass` | MQTT password |

### [Pcwu]

| Key | Description |
|---|---|
| `Device_Pcwu_Enabled` | `True` to activate the heat pump device |
| `Device_Pcwu_Address` | IP address of the RS485-to-TCP gateway |
| `Device_Pcwu_Port` | TCP port of the gateway (default: `8899`) |
| `Device_Pcwu_MqttTopic` | Base MQTT topic (default: `Heatpump`) |
| `Baudrate` | Must match gateway config (default: `38400`) |
| `DebugLogging` | `True` to enable verbose DEBUG output in AppDaemon logs |

### [ZPS] (optional)

For solar boiler controllers. Set `Device_Zps_Enabled = True` and fill in address/port/topic. Currently the ZPS device class is not bundled — this section is reserved for future use.

---

## 6. MQTT topics

All topics use the base topic configured in `Device_Pcwu_MqttTopic` (default: `Heatpump`).

### State topics (published by the app)

| Topic | Type | Description |
|---|---|---|
| `Heatpump/T1` | float (°C) | Ambient temperature |
| `Heatpump/T2` | float (°C) | Floor heating outlet temperature |
| `Heatpump/T3` | float (°C) | Floor heating inlet temperature |
| `Heatpump/T6` | float (°C) | Water pump inlet temperature |
| `Heatpump/T7` | float (°C) | Heat pump outlet temperature |
| `Heatpump/T8` | float (°C) | Evaporator temperature |
| `Heatpump/T9` | float (°C) | Before compressor temperature |
| `Heatpump/T10` | float (°C) | After compressor temperature |
| `Heatpump/EV1` | int | Expansion valve position |
| `Heatpump/HeatPumpEnabled` | bool string | `True` / `False` — pump on/off |
| `Heatpump/CirculationPumpON` | bool string | Circulation pump running |
| `Heatpump/FanON` | bool string | Fan running |
| `Heatpump/HeaterEON` | bool string | Electric heater active |
| `Heatpump/CompressorON` | bool string | Compressor running |
| `Heatpump/WaitingStatus` | string | Device waiting/error state |
| `Heatpump/TapWaterTemp` | float (°C) | Target water temperature |
| `Heatpump/TapWaterHysteresis` | float (°C) | Hysteresis setting |
| `Heatpump/DefrostingInterval` | int (min) | Defrost check interval |
| `Heatpump/DefrostingStartTemp` | float (°C) | Temperature to trigger defrost |
| `Heatpump/DefrostingStopTemp` | float (°C) | Temperature to end defrost |
| `Heatpump/DefrostingMaxTime` | int (min) | Maximum defrost duration |

### Command topics (subscribe to change settings)

Publish to `Heatpump/Command/<register>` to update a writable config register.

| Topic | Example value | Description |
|---|---|---|
| `Heatpump/Command/TapWaterTemp` | `35` | Set target water temperature |
| `Heatpump/Command/TapWaterHysteresis` | `6` | Set hysteresis |
| `Heatpump/Command/DefrostingInterval` | `30` | Set defrost interval (min) |
| `Heatpump/Command/DefrostingStartTemp` | `-5` | Set defrost trigger temperature |
| `Heatpump/Command/DefrostingStopTemp` | `5` | Set defrost stop temperature |
| `Heatpump/Command/DefrostingMaxTime` | `20` | Set max defrost duration (min) |

> **Note:** `HeatPumpEnabled` is intentionally blocked from write-back to prevent unwanted state changes from MQTT retained messages. Use the HA switch entity instead.

---

## 7. Home Assistant integration

Copy `config/packages/hewalex.yaml` to your `/config/packages/` directory.

Enable packages in `configuration.yaml` if not already done:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

The package creates:
- **1 switch** — turn the heat pump on/off
- **17 sensors** — all temperature and status values
- **5 binary sensors** — running states (pump, fan, compressor, heater)
- **2 climate entities** — floor heating temperature control and hysteresis control

All entities are grouped under the `Hewalex Heat Pump` device in Home Assistant.

A virtual `sensor.hewalex_status` entity is maintained by the AppDaemon app itself (not via MQTT). It shows `online` when data is received and switches to `offline` after 5 minutes without a successful RS485 read.

---

## 8. Troubleshooting

**No data in Home Assistant after startup**
- Check AppDaemon logs for `RS485 read error` or `MQTT connect failed`
- Verify the gateway IP and port in `hewalex2mqttconfig.ini`
- Confirm the gateway is reachable: `nc -zv <gateway_ip> 8899`
- Confirm MQTT broker credentials are correct

**`sensor.hewalex_status` shows `offline`**
- No successful RS485 read in the last 5 minutes
- Check physical RS485 wiring and gateway power
- Enable `DebugLogging = True` temporarily and restart AppDaemon

**RS485 blocked for 60 s**
- Logged as: `RS485 blocked for 60 s due to error: ...`
- A hard connection error (timeout, broken pipe, port unavailable) triggered the cooldown
- The app will resume automatically after 60 s

**Write commands are ignored**
- Check that the register name matches exactly (case-sensitive)
- `HeatPumpEnabled` is intentionally blocked — use the HA switch
- Duplicate commands within 10 s are silently ignored

**AppDaemon does not load the app**
- Verify the `apps.yaml` entry matches `module: hewalex2mqtt` and `class: Hewalex2MQTT`
- Ensure `hewalex_geco/` is present in the apps directory alongside `hewalex2mqtt.py`

---

## 9. Credits

- Protocol research and initial implementation: [Jojan265](https://gathering.tweakers.net/forum/view_message/79522762)
- Hewalex GECO protocol library: [Chibald/Hewalex2Mqtt](https://github.com/Chibald/Hewalex2Mqtt)
- AppDaemon integration and production hardening: [HJKLMN](https://github.com/HJKLMN)
