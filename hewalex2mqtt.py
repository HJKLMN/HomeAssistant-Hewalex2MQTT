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

# Versie: 2026-03-20d — paho loop_forever in daemon thread

SOFT_ERRORS = ("Invalid soft message len", "Invalid Const Bytes")

BLOCKED_COMMAND_REGISTERS = frozenset()


class Hewalex2MQTT(hass.Hass):
    """Lees Hewalex warmtepomp via RS485 en publiceer naar MQTT + HA-waarschuwing bij uitval."""

    def initialize(self):
        self.log("Starting Hewalex 2 MQTT")

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

        self._last_command = {}  # {reg: (payload, timestamp)}

        self.initConfiguration()

        self.dev = PCWU(1, 1, 2, 2, self.on_message_serial)
        self.start_mqtt()

        # write-queue + worker-thread
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
        try:
            self.client.disconnect()
        except Exception:
            pass

    # ---------------------------------------------------------------
    # HeatPumpEnabled
    # ---------------------------------------------------------------
    def _handle_heatpump_command(self, payload):
        """Zet de warmtepomp aan of uit via register 304 (enable/disable)."""
        self.log(f"HeatPumpEnabled command -> {payload}")
        if not self._rs485_available():
            self.log("HeatPumpEnabled write overgeslagen: RS485 tijdelijk geblokkeerd")
            return
        ok = False
        try:
            with self.ser_lock:
                with serial.serial_for_url(
                    f"socket://{self._addr}:{self._port}",
                    timeout=5,
                    write_timeout=5,
                ) as ser:
                    if payload == "True":
                        self.dev.enable(ser)
                    else:
                        self.dev.disable(ser)
                ok = True
                time.sleep(0.25)
        except Exception as e:
            self.log(f"HeatPumpEnabled write error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")
        finally:
            self.log(f"HeatPumpEnabled -> {payload} — {'geslaagd' if ok else 'mislukt'}")
        if ok:
            self.run_in(lambda kwargs: self.readPcwuConfig(), 2)

    # ---------------------------------------------------------------
    # Config inlezen
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

        try:
            self._debug = cfg.getboolean("Pcwu", "DebugLogging", fallback=False)
        except TypeError:
            try:
                self._debug = cfg.getboolean("Pcwu", "DebugLogging")
            except Exception:
                self._debug = False

    def dlog(self, msg):
        if getattr(self, "_debug", False):
            self.log(msg, level="DEBUG")

    # ---------------------------------------------------------------
    # MQTT — loop_forever in eigen daemon thread
    # ---------------------------------------------------------------
    def start_mqtt(self):
        with self.mqtt_lock:
            now = time.time()
            if now - self.last_mqtt_restart < 30:
                self.dlog("MQTT reconnect suppressed (too soon)")
                return
            self.last_mqtt_restart = now

        try:
            try:
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

            # loop_forever in daemon thread
            t = threading.Thread(target=self.client.loop_forever, daemon=True)
            t.start()

            self.log("MQTT connected")
        except Exception as e:
            self.log(f"MQTT connect failed: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    def on_connect(self, client, userdata, flags, rc):
        self.log("MQTT: on_connect — subscribing")
        client.subscribe(self._topic + "/Command/#", qos=1)

    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.log(f"MQTT disconnected ({rc}), retrying in 5s")
            t = threading.Timer(5.0, self.start_mqtt)
            t.daemon = True
            t.start()

    # ---------------------------------------------------------------
    # MQTT Callback
    # ---------------------------------------------------------------
    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            topic = msg.topic.split("/")
            if len(topic) == 3 and topic[0] == self._topic and topic[1] == "Command":
                reg = topic[2]

                # HeatPumpEnabled: geen deduplicatie, altijd uitvoeren
                if reg == "HeatPumpEnabled":
                    self._handle_heatpump_command(payload)
                    return

                # Overige registers: deduplicatie binnen 10s
                now = time.time()
                last_payload, last_ts = self._last_command.get(reg, (None, 0))
                if last_payload == payload and (now - last_ts) < 10:
                    self.dlog(f"Command {reg} -> {payload} genegeerd (duplicaat binnen 10s)")
                    return
                self._last_command[reg] = (payload, now)

                if reg in BLOCKED_COMMAND_REGISTERS:
                    self.dlog(f"Command {reg} genegeerd (read-only register)")
                    return

                self.log(f"Command {reg} -> {payload}")
                with self.write_lock:
                    self.write_queue[reg] = payload
        except Exception as e:
            self.log(f"MQTT message error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    # ---------------------------------------------------------------
    # Write-worker
    # ---------------------------------------------------------------
    def write_worker(self):
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
                time.sleep(0.5)

                with self.write_lock:
                    queue_empty = not bool(self.write_queue)
                if queue_empty:
                    self.readPcwuConfig()

            except Exception as e:
                self.log(f"Write worker error: {e}")
                self.log(traceback.format_exc(), level="DEBUG")
                time.sleep(1.0)

    # ---------------------------------------------------------------
    # Config-read callback (periodiek)
    # ---------------------------------------------------------------
    def readPcwuConfig_cb(self, kwargs):
        try:
            if self.writing_active:
                self.dlog("Config-read overgeslagen: write actief")
                return
            if not self._rs485_available():
                self.dlog("Config-read overgeslagen: RS485 tijdelijk geblokkeerd")
                return
            self.readPcwuConfig()
        except Exception as e:
            self.log(f"Deferred config read error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    # ---------------------------------------------------------------
    # Seriele callback
    # ---------------------------------------------------------------
    def on_message_serial(self, obj, h, sh, m):
        try:
            if sh["FNC"] == 0x50:
                mp = obj.parseRegisters(
                    sh["RestMessage"], sh["RegStart"], sh["RegLen"]
                )
                new_values = 0
                for reg, val in mp.items():
                    if isinstance(val, dict):
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
        if self.writing_active:
            self.dlog("Read overgeslagen: write actief")
            return
        if time.time() - self.last_write_time < 10:
            self.dlog("Read overgeslagen: backoff na write")
            return
        if not self._rs485_available():
            self.dlog("Read overgeslagen: RS485 tijdelijk geblokkeerd")
            return
        time.sleep(random.uniform(0.0, 0.3))
        try:
            self.readPCWU()
        except Exception as e:
            self.log(f"Polling error: {e}")
            self.log(traceback.format_exc(), level="DEBUG")

    def watchdog_cb(self, kwargs):
        elapsed = time.time() - self.last_success
        if elapsed > 300 and not self.offline_reported:
            self.offline_reported = True
            self.set_state(
                "sensor.hewalex_status",
                state="offline",
                attributes={"message": "RS485 onbereikbaar >5 min"},
            )
            self.log("RS485-gateway >5 min onbereikbaar — melding aan HA")

    # ---------------------------------------------------------------
    # RS485 helper
    # ---------------------------------------------------------------
    def _rs485_available(self):
        return time.time() >= getattr(self, "rs485_block_until", 0)

    def _handle_rs485_hard_error(self, msg):
        self.rs485_block_until = time.time() + 60
        self.log(f"RS485 tijdelijk geblokkeerd voor 60s wegens fout: {msg}")

    # ---------------------------------------------------------------
    # Lees/schrijf functies met lock
    # ---------------------------------------------------------------
    def readPCWU(self):
        if not self._rs485_available():
            self.dlog("readPCWU overgeslagen: RS485 tijdelijk geblokkeerd")
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
            duur = time.perf_counter() - start
            self.log(f"Read OK - {total} gelezen, {new} nieuw - duur {duur:.2f}s")
        except Exception as e:
            msg = str(e)
            if any(x in msg for x in SOFT_ERRORS):
                self.dlog(f"Leesfout RS485 (zacht): {msg}")
                return
            self.log(f"Leesfout RS485: {msg}")
            self.log(traceback.format_exc(), level="DEBUG")
            if any(x in msg for x in ["disconnected", "Broken", "reset", "timeout", "filedescriptor out of range", "Could not open port"]):
                self._handle_rs485_hard_error(msg)
                t = threading.Timer(5.0, self.start_mqtt)
                t.daemon = True
                t.start()

    def writePcwuConfig(self, reg, payload):
        """Schrijf register naar Hewalex, met lock, rustpauze en duidelijke logging."""
        if not self._rs485_available():
            self.log(f"Write {reg}={payload} overgeslagen: RS485 tijdelijk geblokkeerd")
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
                self.dlog(f"Write (zachte fout) genegeerd: {msg}")
            else:
                self.log(f"Write error: {msg}")
                self.log(traceback.format_exc(), level="DEBUG")
            if any(x in msg for x in ["disconnected", "Broken", "reset", "timeout", "filedescriptor out of range", "Could not open port"]):
                self._handle_rs485_hard_error(msg)
                t = threading.Timer(5.0, self.start_mqtt)
                t.daemon = True
                t.start()
        finally:
            self.writing_active = False
            self.last_write_time = time.time()
            self.log(f"Write {reg}={payload} - {'geslaagd' if ok else 'mislukt'}")

    def readPcwuConfig(self):
        if not self._rs485_available():
            self.dlog("readPcwuConfig overgeslagen: RS485 tijdelijk geblokkeerd")
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
            duur = time.perf_counter() - start
            self.log(f"Config-read voltooid - {total} gelezen, {new} nieuw - duur {duur:.2f}s")
        except Exception as e:
            msg = str(e)
            if any(x in msg for x in SOFT_ERRORS):
                self.dlog(f"Config read (zachte fout) genegeerd: {msg}")
                return
            self.log(f"Config read error: {msg}")
            self.log(traceback.format_exc(), level="DEBUG")
            if any(x in msg for x in ["disconnected", "Broken", "reset", "timeout", "filedescriptor out of range", "Could not open port"]):
                self._handle_rs485_hard_error(msg)
