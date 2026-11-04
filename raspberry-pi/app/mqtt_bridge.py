"""MQTT client for lora.kmitl.ac.th: Pi topics + ChirpStack uplinks of the LoRa node."""
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
TOPIC_LORA_UPLINK = f"application/{config.LORA_APPLICATION_ID}/device/{config.LORA_DEV_EUI}/event/up"


def decode_lora_payload(data_b64):
    """Decodes the raw uplink: [light_raw_hi, light_raw_lo, light_digital]."""
    raw = base64.b64decode(data_b64 or "")
    if len(raw) < 3:
        return {"raw_hex": raw.hex()}
    return {
        "light_raw": (raw[0] << 8) | raw[1],
        "light_digital": raw[2],
    }


def raw_to_lux(light_raw):
    """Estimated lux from the 10-bit analogRead (see LDR_* in config.py), None if out of range."""
    if not 0 < light_raw < 1023:
        return None
    r_ldr = config.LDR_FIXED_OHMS * light_raw / (1023 - light_raw)
    return round(10 * (config.LDR_R10_OHMS / r_ldr) ** (1 / config.LDR_GAMMA), 1)


def parse_chirpstack_uplink(payload):
    """Supports both ChirpStack v4 (deviceInfo/snr) and v3 (devEUI/loRaSNR) JSON."""
    msg = json.loads(payload)
    # Decode the raw bytes ourselves so a mismatched ChirpStack codec can't hide light_raw.
    data = decode_lora_payload(msg.get("data"))
    if "light_raw" not in data and msg.get("object"):
        data = msg["object"]
    if "light_raw" in data:
        data["light_lux"] = raw_to_lux(data["light_raw"])
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


class Broker:
    """Publishes Pi data, caches every message under TOPIC_PREFIX, receives LoRa uplinks."""

    def __init__(self, on_command, on_uplink):
        self.on_command = on_command
        self.on_uplink = on_uplink
        self.lora_enabled = bool(config.LORA_APPLICATION_ID and config.LORA_DEV_EUI)
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
        if self.lora_enabled:
            client.subscribe(TOPIC_LORA_UPLINK, qos=1)
        else:
            print("[mqtt] LORA_APPLICATION_ID / LORA_DEV_EUI not set, not subscribing to LoRa uplinks")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        print(f"[mqtt] {config.MQTT_HOST} disconnected: {reason_code}")

    def _on_message(self, client, userdata, msg):
        if self.lora_enabled and msg.topic == TOPIC_LORA_UPLINK:
            try:
                self.on_uplink(parse_chirpstack_uplink(msg.payload))
            except (ValueError, KeyError, TypeError) as e:
                print(f"[mqtt] bad LoRa uplink: {e}")
            return
        text = msg.payload.decode(errors="replace")
        with self._lock:
            self.messages[msg.topic] = {"payload": text, "retain": msg.retain, "received_at": time.time()}
        if msg.topic == TOPIC_LED_SET:
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

