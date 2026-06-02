"""ESP32Controller — sterowanie elektroniką DIY.

Protokoły: HTTP REST + opcjonalnie MQTT.

Konfiguracja w config.toml:
    [esp32]
    enabled = true
    host = "http://192.168.1.100"

    [[esp32.devices]]
    name = "pompa"
    pin = 2
    type = "relay"
    aliases = ["woda", "nawadnianie"]
"""
from __future__ import annotations
import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.logging_setup import get_logger
log = get_logger(__name__)

try:
    import requests
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

try:
    import paho.mqtt.client as mqtt
    _MQTT_OK = True
except ImportError:
    _MQTT_OK = False


@dataclass
class DevicePin:
    name: str
    pin: int
    type: str = "relay"
    aliases: List[str] = field(default_factory=list)
    inverted: bool = False

    def matches(self, q: str) -> bool:
        q = q.lower().strip()
        return q in self.name.lower() or any(q in a.lower() for a in self.aliases)


@dataclass
class ESP32Result:
    success: bool
    message: str
    raw: Optional[Dict[str, Any]] = None


class ESP32HTTPClient:
    def __init__(self, host: str, timeout: float = 3.0):
        self.host = host.rstrip("/")
        self.timeout = timeout

    def relay(self, pin: int, state: bool) -> ESP32Result:
        return self._get(f"{self.host}/relay", {"pin": pin, "state": "on" if state else "off"})

    def pwm(self, pin: int, value: int) -> ESP32Result:
        return self._get(f"{self.host}/pwm", {"pin": pin, "value": max(0, min(255, value))})

    def adc_read(self, pin: int = 34) -> ESP32Result:
        return self._get(f"{self.host}/adc", {"pin": pin})

    def status(self) -> ESP32Result:
        return self._get(f"{self.host}/status", {})

    def command(self, cmd: str, params: Dict = None) -> ESP32Result:
        if not _REQ_OK:
            return ESP32Result(False, "Brak requests: pip install requests")
        try:
            r = requests.post(f"{self.host}/command",
                              json={"cmd": cmd, "params": params or {}},
                              timeout=self.timeout)
            if r.ok:
                return ESP32Result(True, "OK", r.json() if r.content else None)
            return ESP32Result(False, f"HTTP {r.status_code}")
        except requests.Timeout:
            return ESP32Result(False, "ESP32 timeout")
        except requests.ConnectionError:
            return ESP32Result(False, f"Brak połączenia ({self.host})")
        except Exception as e:
            return ESP32Result(False, str(e))

    def _get(self, url: str, params: Dict) -> ESP32Result:
        if not _REQ_OK:
            return ESP32Result(False, "pip install requests")
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            if r.ok:
                try:
                    data = r.json()
                except Exception:
                    data = {"response": r.text}
                return ESP32Result(True, "OK", data)
            return ESP32Result(False, f"HTTP {r.status_code}: {r.text[:80]}")
        except requests.Timeout:
            return ESP32Result(False, "ESP32 timeout")
        except requests.ConnectionError:
            return ESP32Result(False, f"Brak połączenia ({self.host})")
        except Exception as e:
            return ESP32Result(False, str(e))


class ESP32MQTTClient:
    def __init__(self, cfg, on_status: Optional[Callable] = None):
        self.cfg = cfg
        self.on_status = on_status
        self._client = None
        self._connected = False

    def connect(self) -> bool:
        if not _MQTT_OK:
            log.warning("MQTT: pip install paho-mqtt")
            return False
        try:
            self._client = mqtt.Client(client_id="jarvis", clean_session=True)
            if self.cfg.mqtt_username:
                self._client.username_pw_set(self.cfg.mqtt_username, self.cfg.mqtt_password)
            self._client.on_connect    = self._on_connect
            self._client.on_message    = self._on_message
            self._client.on_disconnect = self._on_disconnect
            self._client.connect(self.cfg.mqtt_broker, self.cfg.mqtt_port, keepalive=60)
            self._client.loop_start()
            for _ in range(20):
                if self._connected: break
                time.sleep(0.1)
            return self._connected
        except Exception as e:
            log.error("MQTT connect: %s", e)
            return False

    def send_command(self, cmd: str, params: Dict = None) -> bool:
        if not self._connected or not self._client:
            return False
        try:
            self._client.publish(
                self.cfg.mqtt_topic_cmd,
                json.dumps({"cmd": cmd, "params": params or {}, "ts": time.time()}),
                qos=1
            )
            return True
        except Exception as e:
            log.error("MQTT publish: %s", e)
            return False

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            client.subscribe(self.cfg.mqtt_topic_status)
            log.info("MQTT połączony: %s", self.cfg.mqtt_broker)
        else:
            log.error("MQTT błąd: rc=%d", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if self.on_status:
                self.on_status(payload)
        except Exception:
            pass

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False


class ESP32Controller:
    """Główny kontroler — HTTP + opcjonalnie MQTT.

    Użycie z Jarvisa:
        ctx.esp32.turn_on("pompa")
        ctx.esp32.turn_off("led")
        ctx.esp32.set_voltage(12.0)
        ctx.esp32.get_status()
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.http = ESP32HTTPClient(cfg.host, cfg.timeout)
        self.mqtt: Optional[ESP32MQTTClient] = None
        self._pin_states: Dict[int, Any] = {}

        if getattr(cfg, "mqtt_enabled", False) and getattr(cfg, "mqtt_broker", ""):
            self.mqtt = ESP32MQTTClient(cfg, on_status=self._on_status_update)
            if self.mqtt.connect():
                log.info("ESP32 MQTT aktywny")

    def turn_on(self, device_query: str) -> ESP32Result:
        device = self._find_device(device_query)
        if device is None:
            return ESP32Result(False,
                f"Nie znam urządzenia: '{device_query}'. Dostępne: {self._device_list()}")
        return self._set_device(device, True)

    def turn_off(self, device_query: str) -> ESP32Result:
        device = self._find_device(device_query)
        if device is None:
            return ESP32Result(False, f"Nie znam urządzenia: '{device_query}'")
        return self._set_device(device, False)

    def set_value(self, device_query: str, value: int) -> ESP32Result:
        device = self._find_device(device_query)
        if device is None:
            device = next((d for d in self.cfg.devices if d.type in ("pwm","dac")), None)
        if device is None:
            return ESP32Result(False, "Brak urządzenia PWM/DAC")
        if device.type == "pwm":
            result = self.http.pwm(device.pin, value)
            if result.success:
                self._pin_states[device.pin] = value
            return result
        return ESP32Result(False, f"'{device.name}' nie obsługuje set_value")

    def set_voltage(self, volts: float) -> ESP32Result:
        max_v = getattr(self.cfg, "max_volts", 12.0)
        pwm_v = int((volts / max_v) * 255)
        pwm_v = max(0, min(255, pwm_v))
        device = next((d for d in self.cfg.devices if d.type in ("pwm","dac")), None)
        if device is None:
            return ESP32Result(False, "Brak urządzenia PWM/DAC w konfiguracji")
        result = self.http.pwm(device.pin, pwm_v)
        if result.success:
            result.message = f"Napięcie ~{volts:.1f}V (PWM={pwm_v})"
        return result

    def get_status(self) -> ESP32Result:
        result = self.http.status()
        if result.success and result.raw:
            self._pin_states.update(result.raw.get("pins", {}))
        return result

    def handle_intent(self, intent) -> str:
        """Wywołuje odpowiednią akcję na podstawie IntentType."""
        from ai.intent import IntentType
        typ = intent.typ

        if typ == IntentType.ESP32_ON:
            name = self._extract_device_name(intent.tresc)
            r = self.turn_on(name)
            return r.message if r.success else f"❌ {r.message}"

        elif typ == IntentType.ESP32_OFF:
            name = self._extract_device_name(intent.tresc)
            r = self.turn_off(name)
            return r.message if r.success else f"❌ {r.message}"

        elif typ == IntentType.ESP32_SET:
            param   = intent.param
            wartosc = intent.wartosc
            try:
                val = float(wartosc.replace(",", "."))
            except ValueError:
                return f"Nie rozumiem wartości: '{wartosc}'"
            if any(w in param for w in ("napiecie","napięcie","voltage")):
                r = self.set_voltage(val)
            elif any(w in param for w in ("jasność","brightness")):
                r = self.set_value("led", int(val / 100 * 255))
            else:
                r = self.set_value(param, int(val))
            return r.message if r.success else f"❌ {r.message}"

        elif typ == IntentType.ESP32_STATUS:
            r = self.get_status()
            if not r.success:
                return f"❌ ESP32: {r.message}"
            pins = r.raw.get("pins", {}) if r.raw else {}
            if not pins:
                return "ESP32 odpowiada, brak danych pinów."
            lines = ["Stan ESP32:"]
            for d in self.cfg.devices:
                state = pins.get(str(d.pin), "?")
                icon = "🟢" if state in (1, True, "on", "1") else "🔴"
                lines.append(f"  {icon} {d.name} (pin {d.pin}): {state}")
            return "\n".join(lines)

        elif typ == IntentType.ESP32_LIST:
            lines = ["Znane urządzenia ESP32:"]
            for d in self.cfg.devices:
                al = f" ({', '.join(d.aliases)})" if d.aliases else ""
                lines.append(f"  • {d.name} — pin {d.pin}, typ: {d.type}{al}")
            return "\n".join(lines)

        return "Nieznana komenda ESP32."

    def _find_device(self, query: str) -> Optional[DevicePin]:
        q = query.lower().strip()
        for d in self.cfg.devices:
            if d.matches(q):
                return d
        for d in self.cfg.devices:
            if q in d.name.lower() or any(q in a.lower() for a in d.aliases):
                return d
        return None

    def _extract_device_name(self, text: str) -> str:
        cleaned = re.sub(
            r"\b(włącz|wyłącz|zapal|zgaś|aktywuj|dezaktywuj|otwórz|zamknij)\b",
            "", text, flags=re.IGNORECASE
        ).strip()
        return cleaned.strip()

    def _set_device(self, device: DevicePin, state: bool) -> ESP32Result:
        real = not state if device.inverted else state
        r = self.http.relay(device.pin, real)
        if r.success:
            self._pin_states[device.pin] = real
            action = "włączony" if state else "wyłączony"
            r.message = f"✅ {device.name.capitalize()} {action}."
            if self.mqtt and self.mqtt._connected:
                self.mqtt.send_command("relay", {"pin": device.pin, "state": "on" if real else "off"})
        return r

    def _device_list(self) -> str:
        return ", ".join(d.name for d in self.cfg.devices)

    def _on_status_update(self, payload: dict) -> None:
        self._pin_states.update(payload.get("pins", {}))
