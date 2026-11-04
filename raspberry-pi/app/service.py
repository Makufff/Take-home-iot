"""Core logic shared by the REST API and the MCP tools."""
import threading
import time
from collections import deque

from . import config
from .hardware import PiDevices
from .mqtt_bridge import (
    TOPIC_DISTANCE,
    TOPIC_HUMIDITY,
    TOPIC_LED,
    TOPIC_LED_SET,
    TOPIC_LORA_DATA,
    TOPIC_TEMPERATURE,
    Broker,
)

HISTORY_SIZE = 720  # 1 hour at a 5 s sample interval


def _parse_on(text):
    return str(text).strip().lower() in ("1", "on", "true")


class IoTService:
    def __init__(self):
        self.devices = PiDevices()
        self.mqtt = Broker(on_command=self._on_mqtt_command, on_uplink=self._on_lora_uplink)
        self.history = deque(maxlen=HISTORY_SIZE)
        self.pi = {"temperature": None, "humidity": None, "distance": None, "updated_at": None}
        self.lora_node = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)

    def start(self):
        self.mqtt.start()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.mqtt.stop()
        self.devices.close()

    # Raspberry Pi
    def read_pi_sensors(self):
        values = self.devices.read_sensors()
        self.pi = {**values, "updated_at": time.time()}
        self.history.append(dict(self.pi))
        for name, t in (("temperature", TOPIC_TEMPERATURE), ("humidity", TOPIC_HUMIDITY), ("distance", TOPIC_DISTANCE)):
            if values[name] is not None:
                self.mqtt.publish(t, str(values[name]), retain=True)
        return self.pi

    def set_pi_led(self, on):
        state = self.devices.set_led(on)
        self.mqtt.publish(TOPIC_LED, "on" if state else "off", retain=True)
        return state

    def _sample_loop(self):
        while not self._stop.is_set():
            try:
                self.read_pi_sensors()
            except Exception as e:  # keep sampling even if one read fails
                print(f"[service] sample error: {e}")
            self._stop.wait(config.SAMPLE_INTERVAL)

    # LoRa node
    def _on_lora_uplink(self, data):
        self.lora_node = data
        self.mqtt.publish(TOPIC_LORA_DATA, data, retain=True)

    # MQTT commands from other clients
    def _on_mqtt_command(self, topic_name, payload):
        try:
            if topic_name == TOPIC_LED_SET:
                self.set_pi_led(_parse_on(payload))
        except Exception as e:
            print(f"[service] command {topic_name} failed: {e}")

    def status(self):
        return {
            "pi": {**self.pi, "led": self.devices.led},
            "lora": {
                "node": self.lora_node,
                "enabled": self.mqtt.lora_enabled,
            },
            "mqtt": {"host": config.MQTT_HOST, "connected": self.mqtt.connected, "prefix": config.TOPIC_PREFIX},
            "simulate": config.SIMULATE,
        }
