import appdaemon.plugins.hass.hassapi as hass
import configparser
import serial
from hewalex_geco.devices import PCWU
import paho.mqtt.client as mqtt
import time
import traceback
import datetime
import random
import threading

# Registers received via MQTT Command that must NOT be written to the device.
# HeatPumpEnabled is managed as an on/off switch via the HA switch entity.
# Blocking it here prevents unwanted writes on retained-message redelivery.
BLOCKED_COMMAND_REGISTERS = frozenset({"HeatPumpEnabled"})

# RS485 soft errors that are safe to ignore (no reconnect needed)
SOFT_ERRORS = ("Invalid soft message len", "Invalid Const Bytes")


class Hewalex2MQTT(hass.Hass):
    """AppDaemon app: read Hewalex heat pump via RS485/TCP and publish to MQTT.

    Features:
    - Periodic status poll (every 60 s) and config poll (every 10 min)
    - Thread-safe serial and MQTT access via locks
    - Write queue: last-write-wins, worker thread handles writes asynchronously
    - Watchdog: reports sensor.hewalex_status = offline after 5 min without data
    - RS485 backoff: 60 s cooldown after hard connection errors
    - Duplicate command suppression: same register+value within 10 s is ignored
    """

    def initialize(self):
        self.log("Starting Hewalex2MQTT")

        self.MessageCache = {}
        self.ser_lock = threading.Lock()
        self.mqtt_lock = threading.Lock()
        self._last_read_count = 0
        self._last_new_count = 0

        self.last_mqtt_restart = 0
        self.last_success = time.time()
        self.offline_reported = False
        self.writing_active = False
        self.last_write_time = 0
        self.rs485_block_until = 0

        # Deduplication: track last command per register {reg: (payload, timestamp)}
        self._last_command = {}

        self.initConfiguration()

        self.dev = PCWU(1, 1, 2, 2, self.on_message_serial)
        self.start_mqtt()

        # Write queue + worker thread
        self.write_queue = {}
        self.write_lock = threading.Lock()
        self.write_thread_stop = threading.Event()
        self.write_thread = threading.Thread(target=self.write_worker, daemon=True)
        self.write_thread.start()

        start_poll = self.datetime() + datetime.timedelta(seconds=5)
        start_watchdog = self.datetime() + datetime.timedelta(seconds=60)
        start_config = self.datetime() + datetime.timedelta(seconds=90)

        self.poll_handle = self.run_every(self.readPCWU_cb, start_poll, 60)
        self.watchdog_handle = self.run_every(self.watchdog_cb, start_watchdog, 60)
        self.config_refresh_handle = self.run_every(
            self.readPcwuConfig_cb, start_config, 600
        )

        self.log("Config-read interval: 10 min")

    def terminate(self):
        try:
            self.write_thread_stop.set()
        except Exception:
            pass

    # ---------------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------------
    def initConfiguration(self):
        cfg = configparser.ConfigParser()
        cfg.read("/config/apps/hewalex2mqttconfig.ini")

        self._MQTT_ip = cfg["MQTT"]["MQTT_ip"]
        self._MQTT_port = cfg.getint("MQTT", "MQTT_port")
        self._MQTT_auth = cfg.getboolean("MQTT", "MQTT_authentication")
        self._MQTT_user = cfg["MQTT"]["MQTT_user"]
        self._MQTT_pass = cfg["MQTT"]["MQTT_pass"]

        self._addr = cfg["Pcwu"]["Device_Pcwu_Address"]
        self._port = cfg["Pcwu"]["Device_Pcwu_Port"]
        self._topic = cfg["Pcwu"]["Device_Pcwu_MqttTopic"]
        self._enabled = cfg.getboolean("Pcwu", "Device_Pcwu_Enabled")

        # Optional debug logging (set DebugLogging = True in [Pcwu] section)
        try:
            self._debug = cfg.getboolean("Pcwu", "DebugLogging", fallback=False)
        except TypeError:
            try:
                self._debug = cfg.getboolean("Pcwu", "DebugLogging")
            except Exception:
                self._debug = False

    def dlog(self, msg):
        """Log only when DebugLogging is enabled."""
        if getattr(self, "_debug", False):
            self.log(msg, level="DEBUG")

    # ---------------------------------------------------------------
    # MQTT
    # ---------------------------------------------------------------
    def start_mqtt(self):
        """Connect or reconnect the MQTT client. Rate-limited to once per 30 s."""
        with self.mqtt_lock:
            now = time.time()
            if now - self.last_mqtt_restart < 30:
                self.dlog("MQTT reconnect suppressed (too soon)")
                return
            self.last_mqtt_restart = now

        try:
            try:
                self.client.loop_stop(force=True)
                self.client.disconnect()
            except Exception:
                pass

            self.client = mqtt.Client(clean_session=True)
            if self._MQTT_auth:
                self.client.username_pw_set(self._MQTT_user, self._MQTT_pass)

            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message

            self.client.connect(self._MQTT_ip, self._MQTT_port, keepalive=60)
            self.client.subscribe(self._topic + "/Command/#", qos=1)
            self.client.loop_start()

            self.log("MQTT connected")
        except Exception as e:
            self.log(f"MQTT connect failed: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    def on_connect(self, client, userdata, flags, rc):
        self.dlog(f"MQTT: Connected (rc={rc})")

    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.log(f"MQTT disconnected ({rc}), retrying in 5 s")
            t = threading.Timer(5.0, self.start_mqtt)
            t.daemon = True
            t.start()

    # ---------------------------------------------------------------
    # MQTT incoming command handler
    # ---------------------------------------------------------------
    def on_message(self, client, userdata, msg):
        """Handle incoming MQTT command messages on <topic>/Command/<register>."""
        try:
            payload = msg.payload.decode()
            topic = msg.topic.split("/")
            if len(topic) == 3 and topic[0] == self._topic and topic[1] == "Command":
                reg = topic[2]
                now = time.time()

                # Suppress duplicate commands within 10 s
                last_payload, last_ts = self._last_command.get(reg, (None, 0))
                if last_payload == payload and (now - last_ts) < 10:
                    self.dlog(f"Command {reg} -> {payload} ignored (duplicate within 10 s)")
                    return

                # Block read-only registers
                if reg in BLOCKED_COMMAND_REGISTERS:
                    self.dlog(f"Command {reg} ignored (read-only register)")
                    return

                self._last_command[reg] = (payload, now)
                self.log(f"Command queued: {reg} -> {payload}")

                # Queue the write; last value wins if multiple arrive before processing
                with self.write_lock:
                    self.write_queue[reg] = payload
        except Exception as e:
            self.log(f"MQTT message error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    # ---------------------------------------------------------------
    # Write worker thread
    # ---------------------------------------------------------------
    def write_worker(self):
        """Background thread: drain write_queue and send commands to the device."""
        while not self.write_thread_stop.is_set():
            try:
                item = None
                with self.write_lock:
                    if self.write_queue:
                        reg, payload = self.write_queue.popitem()
                        item = (reg, payload)

                if not item:
                    time.sleep(0.1)
                    continue

                reg, payload = item
                self.writePcwuConfig(reg, payload)

                # Brief pause between writes to the RS485 gateway
                time.sleep(0.5)

                # Verify written value by triggering a config read
                with self.write_lock:
                    queue_empty = not bool(self.write_queue)
                if queue_empty:
                    self.readPcwuConfig()

            except Exception as e:
                self.log(f"Write worker error: {e}")
                self.log(traceback.format_exc(), level="DEBUG")
                time.sleep(1.0)

    # ---------------------------------------------------------------
    # Config read callback (periodic)
    # ---------------------------------------------------------------
    def readPcwuConfig_cb(self, kwargs):
        try:
            if self.writing_active:
                self.dlog("Config read skipped: write in progress")
                return
            if not self._rs485_available():
                self.dlog("Config read skipped: RS485 temporarily blocked")
                return
            self.readPcwuConfig()
        except Exception as e:
            self.log(f"Deferred config read error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    # ---------------------------------------------------------------
    # Serial data callback
    # ---------------------------------------------------------------
    def on_message_serial(self, obj, h, sh, m):
        """Called by hewalex_geco for each RS485 response frame."""
        try:
            if sh["FNC"] == 0x50:
                mp = obj.parseRegisters(
                    sh["RestMessage"], sh["RegStart"], sh["RegLen"]
                )
                new_values = 0
                for reg, val in mp.items():
                    if isinstance(val, dict):
                        # Skip time-program dictionaries
                        continue
                    key = f"{self._topic}/{reg}"
                    val_str = str(val)
                    if self.MessageCache.get(key) != val_str:
                        self.MessageCache[key] = val_str
                        new_values += 1
                        self.client.publish(key, val_str, retain=True)

                self.last_success = time.time()
                self.offline_reported = False
                self.set_state("sensor.hewalex_status", state="online")

                self._last_read_count = len(mp)
                self._last_new_count = new_values

        except Exception as e:
            self.log(f"Serial parse error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    # ---------------------------------------------------------------
    # Polling & watchdog
    # ---------------------------------------------------------------
    def readPCWU_cb(self, kwargs):
        """Periodic status poll callback."""
        if self.writing_active:
            self.dlog("Poll skipped: write in progress")
            return
        if time.time() - self.last_write_time < 10:
            self.dlog("Poll skipped: backoff after write")
            return
        if not self._rs485_available():
            self.dlog("Poll skipped: RS485 temporarily blocked")
            return

        # Small random jitter to reduce collision risk with other processes
        time.sleep(random.uniform(0.0, 0.3))

        try:
            self.readPCWU()
        except Exception as e:
            self.log(f"Polling error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    def watchdog_cb(self, kwargs):
        """Mark sensor.hewalex_status offline if no RS485 data for >5 min."""
        elapsed = time.time() - self.last_success
        if elapsed > 300 and not self.offline_reported:
            self.offline_reported = True
            self.set_state(
                "sensor.hewalex_status",
                state="offline",
                attributes={"message": "RS485 unreachable >5 min"},
            )
            self.log("RS485 gateway unreachable >5 min — reporting offline to HA")

    # ---------------------------------------------------------------
    # RS485 availability helper
    # ---------------------------------------------------------------
    def _rs485_available(self):
        """Return True if the RS485 cooldown period has elapsed."""
        return time.time() >= getattr(self, "rs485_block_until", 0)

    def _handle_rs485_hard_error(self, msg):
        """Block RS485 operations for 60 s after a hard connection error."""
        self.rs485_block_until = time.time() + 60
        self.log(f"RS485 blocked for 60 s due to error: {msg}")

    # ---------------------------------------------------------------
    # Read / write with lock
    # ---------------------------------------------------------------
    def readPCWU(self):
        """Read status registers from the heat pump."""
        if not self._rs485_available():
            self.dlog("readPCWU skipped: RS485 temporarily blocked")
            return

        start = time.perf_counter()
        try:
            with self.ser_lock:
                with serial.serial_for_url(
                    f"socket://{self._addr}:{self._port}", timeout=5
                ) as ser:
                    self.dev.readStatusRegisters(ser)
                time.sleep(0.25)

            total = getattr(self, "_last_read_count", 0)
            new = getattr(self, "_last_new_count", 0)
            elapsed = time.perf_counter() - start
            self.log(f"Read OK — {total} registers, {new} new — {elapsed:.2f} s")

        except Exception as e:
            msg = str(e)
            if any(x in msg for x in SOFT_ERRORS):
                self.dlog(f"RS485 soft error (ignored): {msg}")
                return

            self.log(f"RS485 read error: {msg}")
            self.log(traceback.format_exc(), level="DEBUG")

            if any(
                x in msg
                for x in [
                    "disconnected", "Broken", "reset", "timeout",
                    "filedescriptor out of range", "Could not open port",
                ]
            ):
                self._handle_rs485_hard_error(msg)
                try:
                    self.client.loop_stop(force=True)
                    self.client.disconnect()
                except Exception:
                    pass
                t = threading.Timer(5.0, self.start_mqtt)
                t.daemon = True
                t.start()

    def writePcwuConfig(self, reg, payload):
        """Write a single config register to the heat pump."""
        if not self._rs485_available():
            self.log(f"Write {reg}={payload} skipped: RS485 temporarily blocked")
            return

        self.writing_active = True
        ok = False
        try:
            with self.ser_lock:
                with serial.serial_for_url(
                    f"socket://{self._addr}:{self._port}",
                    timeout=5,
                    write_timeout=5,
                    inter_byte_timeout=0.5,
                    rtscts=False,
                    dsrdtr=False,
                ) as ser:
                    dev = PCWU(1, 1, 2, 2, self.on_message_serial)
                    dev.write(ser, reg, payload)
                ok = True
                time.sleep(0.25)

        except Exception as e:
            msg = str(e)
            if any(x in msg for x in SOFT_ERRORS):
                self.dlog(f"Write soft error (ignored): {msg}")
            else:
                self.log(f"Write error: {msg}")
                self.log(traceback.format_exc(), level="DEBUG")

            if any(
                x in msg
                for x in [
                    "disconnected", "Broken", "reset", "timeout",
                    "filedescriptor out of range", "Could not open port",
                ]
            ):
                self._handle_rs485_hard_error(msg)
                try:
                    self.client.loop_stop(force=True)
                    self.client.disconnect()
                except Exception:
                    pass
                t = threading.Timer(5.0, self.start_mqtt)
                t.daemon = True
                t.start()

        finally:
            self.writing_active = False
            self.last_write_time = time.time()
            self.log(f"Write {reg}={payload} — {'OK' if ok else 'FAILED'}")

    def readPcwuConfig(self):
        """Read configuration registers from the heat pump."""
        if not self._rs485_available():
            self.dlog("readPcwuConfig skipped: RS485 temporarily blocked")
            return

        start = time.perf_counter()
        try:
            with self.ser_lock:
                with serial.serial_for_url(
                    f"socket://{self._addr}:{self._port}", timeout=5
                ) as ser:
                    dev = PCWU(1, 1, 2, 2, self.on_message_serial)
                    dev.readConfigRegisters(ser)
                time.sleep(0.25)

            total = getattr(self, "_last_read_count", 0)
            new = getattr(self, "_last_new_count", 0)
            elapsed = time.perf_counter() - start
            self.log(
                f"Config read OK — {total} registers, {new} new — {elapsed:.2f} s"
            )

        except Exception as e:
            msg = str(e)
            if any(x in msg for x in SOFT_ERRORS):
                self.dlog(f"Config read soft error (ignored): {msg}")
                return

            self.log(f"Config read error: {msg}")
            self.log(traceback.format_exc(), level="DEBUG")

            if any(
                x in msg
                for x in [
                    "disconnected", "Broken", "reset", "timeout",
                    "filedescriptor out of range", "Could not open port",
                ]
            ):
                self._handle_rs485_hard_error(msg)
