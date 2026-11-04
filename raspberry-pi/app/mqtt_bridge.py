"""MQTT clients: HiveMQ (main broker) and ChirpStack (lora.kmitl.ac.th)."""
import base64
import json
import threading
import time

import paho.mqtt.client as mqtt

from . import config


def topic(name):
    return f"{config.TOPIC_PREFIX}/{name}" if config.TOPIC_PREFIX else name


TOPIC_TEMPERATURE = topic("pi/sensor/temperature")
TOPIC_HUMIDITY = topic("pi/sensor/humidity")
TOPIC_DISTANCE = topic("pi/sensor/distance")
TOPIC_LED = topic("pi/device/led")
TOPIC_LED_SET = topic("pi/device/led/set")
TOPIC_STATUS = topic("pi/status")
TOPIC_LORA_DATA = topic("lora/node1/data")
TOPIC_LORA_LED_SET = topic("lora/node1/led/set")


def decode_lora_payload(data_b64):
    """Fallback decoder when ChirpStack has no codec (see arduino-lora/chirpstack-codec.js)."""
    raw = base64.b64decode(data_b64 or "")
    if len(raw) < 4:
        return {"raw_hex": raw.hex()}
    return {
        "light_raw": (raw[0] << 8) | raw[1],
        "light_digital": raw[2],
        "led": raw[3] == 1,
    }


def parse_chirpstack_uplink(payload):
    """Supports both ChirpStack v4 (deviceInfo/snr) and v3 (devEUI/loRaSNR) JSON."""
    msg = json.loads(payload)
    data = msg.get("object") or decode_lora_payload(msg.get("data"))
    rx = (msg.get("rxInfo") or [{}])[0]
    dev_eui = msg.get("deviceInfo", {}).get("devEui") or msg.get("devEUI")
    return {
        **data,
        "dev_eui": dev_eui,
        "f_cnt": msg.get("fCnt"),
        "rssi": rx.get("rssi"),
        "snr": rx.get("snr", rx.get("loRaSNR")),
        "received_at": time.time(),
    }


class MainBroker:
    """HiveMQ client: publishes Pi data, caches every message under TOPIC_PREFIX."""

    def __init__(self, on_command):
        self.on_command = on_command
        self.messages = {}
        self._lock = threading.Lock()
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.will_set(TOPIC_STATUS, payload="offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self):
        self.client.connect_async(config.MQTT_HOST, config.MQTT_PORT)
        self.client.loop_start()

    def stop(self):
        self.client.publish(TOPIC_STATUS, "offline", qos=1, retain=True)
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        print(f"[mqtt] {config.MQTT_HOST} connected: {reason_code}")
        client.publish(TOPIC_STATUS, "online", qos=1, retain=True)
        client.subscribe(topic("#") if config.TOPIC_PREFIX else "#", qos=1)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        print(f"[mqtt] {config.MQTT_HOST} disconnected: {reason_code}")

    def _on_message(self, client, userdata, msg):
        text = msg.payload.decode(errors="replace")
        with self._lock:
            self.messages[msg.topic] = {"payload": text, "retain": msg.retain, "received_at": time.time()}
        if msg.topic in (TOPIC_LED_SET, TOPIC_LORA_LED_SET):
            self.on_command(msg.topic, text)

    def publish(self, topic_name, payload, retain=False):
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        info = self.client.publish(topic_name, payload, qos=1, retain=retain)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def get(self, topic_name):
        with self._lock:
            return self.messages.get(topic_name)

    def topics(self):
        with self._lock:
            return sorted(self.messages)


class LoraBroker:
    """ChirpStack MQTT integration: uplink subscribe + downlink publish."""

    def __init__(self, on_uplink):
        self.on_uplink = on_uplink
        self.connected = False
        self.enabled = bool(config.LORA_APPLICATION_ID and config.LORA_DEV_EUI)
        base = f"application/{config.LORA_APPLICATION_ID}/device/{config.LORA_DEV_EUI}"
        self.topic_up = f"{base}/event/up"
        self.topic_down = f"{base}/command/down"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if config.LORA_MQTT_USER:
            self.client.username_pw_set(config.LORA_MQTT_USER, config.LORA_MQTT_PASS)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self):
        if not self.enabled:
            print("[lora] LORA_APPLICATION_ID / LORA_DEV_EUI not set, LoRa bridge disabled")
            return
        self.client.connect_async(config.LORA_MQTT_HOST, config.LORA_MQTT_PORT)
        self.client.loop_start()

    def stop(self):
        if self.enabled:
            self.client.loop_stop()
            self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        print(f"[lora] {config.LORA_MQTT_HOST} connected: {reason_code}")
        client.subscribe(self.topic_up, qos=1)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        print(f"[lora] {config.LORA_MQTT_HOST} disconnected: {reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            self.on_uplink(parse_chirpstack_uplink(msg.payload))
        except (ValueError, KeyError, TypeError) as e:
            print(f"[lora] bad uplink: {e}")

    def send_downlink(self, data: bytes):
        if not self.enabled:
            raise RuntimeError("LoRa bridge is not configured (LORA_APPLICATION_ID / LORA_DEV_EUI)")
        payload = {
            "devEui": config.LORA_DEV_EUI,
            "confirmed": False,
            "fPort": config.LORA_FPORT,
            "data": base64.b64encode(data).decode(),
        }
        info = self.client.publish(self.topic_down, json.dumps(payload), qos=1)
        return info.rc == mqtt.MQTT_ERR_SUCCESS
