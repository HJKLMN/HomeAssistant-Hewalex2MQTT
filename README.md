# HomeAssistant-Hewalex2MQTT

AppDaemon-based MQTT gateway to integrate Hewalex heat pumps into Home Assistant.
Reads status and config registers from the heat pump via RS485/TCP and publishes them as MQTT topics. Also supports writing config registers (e.g. target temperature) back to the device.

Based on the work by [Jojan265](https://gathering.tweakers.net/forum/view_message/79522762) and [Chibald/Hewalex2Mqtt](https://github.com/Chibald/Hewalex2Mqtt).

---

## 1. What does this do

- Connects to a Hewalex PCWU heat pump via an RS485-to-TCP gateway
- Polls status registers every 60 seconds and config registers every 10 minutes
- Publishes all register values as MQTT topics under a configurable base topic (e.g. `Heatpump/T1`, `Heatpump/HeatPumpEnabled`)
- Subscribes to `<topic>/Command/<register>` for write-back (e.g. setting target temperature)
- Reports online/offline status to Home Assistant via `sensor.hewalex_status`
- Handles RS485 errors gracefully: soft errors are ignored, hard errors trigger a 60s backoff and MQTT reconnect

---

## 2. Requirements

**Hardware**
- Hewalex PCWU heat pump with RS485 port (GeCo controller)
- RS485-to-TCP gateway (see section 3)

**Software**
- Home Assistant with the [AppDaemon add-on](https://github.com/hassio-addons/addon-appdaemon)
- MQTT broker (e.g. Mosquitto add-on)
- Python packages (installed in the AppDaemon environment):
  - `pyserial`
  - `paho-mqtt`

---

## 3. Hardware options for RS485 connection

The heat pump communicates via RS485 at 38400 baud. You need a gateway that exposes this as a TCP socket.

| Option | Notes |
|---|---|
| Waveshare RS485 TO ETH | Recommended. Configure in TCP Server mode, port 8899. |
| USR-TCP232-304 | Similar setup, works well. |
| Direct USB-serial (pyserial) | Possible but requires code change: replace `socket://` URL with serial port path. |

Wiring: connect the RS485 A/B terminals of the gateway to the RS485 port on the GeCo controller board of the heat pump.

---

## 4. Installation

1. Install the AppDaemon add-on in Home Assistant.

2. Copy the following files to your AppDaemon apps directory (typically `/config/appdaemon/apps/` or `/addon_configs/a0d7b954_appdaemon/apps/`):
   - `hewalex2mqtt.py`
   - `hewalex2mqttconfig.ini` (copy from `hewalex2mqttconfig.ini.example` and fill in your values)
   - The `hewalex_geco/` directory (contains the RS485 protocol library)

3. Add the app to your AppDaemon `apps.yaml`:

```yaml
hewalex2mqtt:
  module: hewalex2mqtt
  class: Hewalex2MQTT
```

4. Copy `config/packages/hewalex.yaml` to your Home Assistant packages directory and make sure packages are enabled in `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

5. Restart AppDaemon. Check the AppDaemon log for `Starting Hewalex 2 MQTT` and `MQTT connected`.

---

## 5. Configuration

Copy `hewalex2mqttconfig.ini.example` to `hewalex2mqttconfig.ini` and set your values.

```ini
[MQTT]
MQTT_ip = 192.168.1.100       # IP of your MQTT broker
MQTT_port = 1883
MQTT_authentication = True
MQTT_user = youruser
MQTT_pass = yourpassword

[Pcwu]
Device_Pcwu_Enabled = True
Device_Pcwu_Address = 192.168.1.50  # IP of RS485-to-TCP gateway
Device_Pcwu_Port = 8899             # TCP port on gateway
Device_Pcwu_MqttTopic = Heatpump   # Base MQTT topic
Baudrate = 38400
Bytesize = 8
Parity = NONE
Stopbits = 1
Timeout = 1
DebugLogging = False                # Set True for verbose logging
```

The `[ZPS]` section is for a solar boiler controller (not a heat pump). Set `Device_Zps_Enabled = False` unless you have one.

---

## 6. MQTT topics

All topics use the base topic configured in `Device_Pcwu_MqttTopic` (default: `Heatpump`).

### State topics (published by the app)

| Topic | Type | Description |
|---|---|---|
| `Heatpump/T1` | float | Ambient temperature (°C) |
| `Heatpump/T2` | float | Floor heating outlet (°C) |
| `Heatpump/T3` | float | Floor heating inlet (°C) |
| `Heatpump/T6` | float | Water pump inlet (°C) |
| `Heatpump/T7` | float | Heat pump outlet (°C) |
| `Heatpump/T8` | float | Evaporator (°C) |
| `Heatpump/T9` | float | Before compressor (°C) |
| `Heatpump/T10` | float | After compressor (°C) |
| `Heatpump/EV1` | int | Expansion valve position |
| `Heatpump/HeatPumpEnabled` | bool | Heat pump on/off |
| `Heatpump/CompressorON` | bool | Compressor running |
| `Heatpump/CirculationPumpON` | bool | Circulation pump running |
| `Heatpump/FanON` | bool | Fan running |
| `Heatpump/HeaterEON` | bool | Electric heater active |
| `Heatpump/WaitingStatus` | string | Waiting/error status |
| `Heatpump/TapWaterTemp` | float | Target temperature setpoint (°C) |
| `Heatpump/TapWaterHysteresis` | float | Hysteresis (°C) |
| `Heatpump/DefrostingInterval` | int | Defrost interval (min) |
| `Heatpump/DefrostingStartTemp` | float | Defrost start temperature (°C) |
| `Heatpump/DefrostingStopTemp` | float | Defrost stop temperature (°C) |
| `Heatpump/DefrostingMaxTime` | int | Max defrost duration (min) |

### Command topics (subscribed by the app)

Send a value to `Heatpump/Command/<register>` to write it to the device.

| Topic | Example payload | Description |
|---|---|---|
| `Heatpump/Command/TapWaterTemp` | `35` | Set target temperature |
| `Heatpump/Command/TapWaterHysteresis` | `5` | Set hysteresis |
| `Heatpump/Command/DefrostingInterval` | `60` | Set defrost interval |

Note: `Heatpump/Command/HeatPumpEnabled` is blocked at the app level. Use the MQTT switch in the HA package instead.

---

## 7. Home Assistant integration

The `config/packages/hewalex.yaml` package file creates all entities automatically using MQTT discovery-style manual config. Place it in your HA packages directory.

It creates:
- 1 switch (`Warmtepomp Aan`) — controls `HeatPumpEnabled`
- 16 sensors — all temperature, status and config registers
- 5 binary sensors — compressor, fan, circulation pump, heater, heat pump status
- 2 climate entities — target temperature control and hysteresis control

All entities are grouped under the device `Warmtepomp Hewalex` in the HA device registry.

The app also creates `sensor.hewalex_status` directly via AppDaemon with state `online` / `offline`.

---

## 8. Troubleshooting

**No data appearing in HA**
- Check AppDaemon log for `MQTT connected` and `Read OK`
- Verify `Device_Pcwu_Address` and port are reachable from the HA host
- Check that the RS485 gateway is in TCP Server mode

**`sensor.hewalex_status` shows `offline`**
- No successful RS485 read for >5 minutes
- Check network connectivity to the RS485 gateway
- Check AppDaemon log for RS485 error messages

**RS485 blocked for 60s**
- A hard connection error was detected (timeout, broken pipe, etc.)
- The app will automatically retry after 60 seconds
- If it keeps happening: check cable, gateway power, and port configuration

**MQTT reconnect loop**
- Check broker IP, port, and credentials in `hewalex2mqttconfig.ini`
- Reconnects are rate-limited to once per 30 seconds

**Commands not being written**
- Check AppDaemon log for `Command <reg> -> <value>` and the subsequent `Write <reg>=<value> - OK`
- If `FAILED`: check RS485 connectivity
- `HeatPumpEnabled` commands are intentionally blocked at the app level

---

## 9. Credits

Based on:
- [Jojan265](https://gathering.tweakers.net/forum/view_message/79522762) — original reverse engineering of the Hewalex GeCo RS485 protocol
- [Chibald/Hewalex2Mqtt](https://github.com/Chibald/Hewalex2Mqtt) — Python library (`hewalex_geco`)
