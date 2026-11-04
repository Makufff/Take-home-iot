import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Run without real GPIO (for development on a laptop)
SIMULATE = _bool("SIMULATE")

# GPIO (BCM numbering) - reference/port-connect.txt
PIN_TRIGGER = 14
PIN_ECHO = 15
PIN_LED = 23
PIN_SHT15_DATA = 2
PIN_SHT15_SCK = 3

SAMPLE_INTERVAL = float(os.getenv("SAMPLE_INTERVAL", "5"))

# HTTP server (REST API + MCP + dashboard)
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
DASHBOARD_DIR = Path(os.getenv("DASHBOARD_DIR", BASE_DIR.parent / "dashboard"))

# Main MQTT broker (HiveMQ public broker)
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt-dashboard.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_PREFIX = os.getenv("TOPIC_PREFIX", "take-home-iot").strip("/")

# ChirpStack MQTT (lora.kmitl.ac.th)
LORA_MQTT_HOST = os.getenv("LORA_MQTT_HOST", "lora.kmitl.ac.th")
LORA_MQTT_PORT = int(os.getenv("LORA_MQTT_PORT", "1883"))
LORA_MQTT_USER = os.getenv("LORA_MQTT_USER", "")
LORA_MQTT_PASS = os.getenv("LORA_MQTT_PASS", "")
LORA_APPLICATION_ID = os.getenv("LORA_APPLICATION_ID", "")
LORA_DEV_EUI = os.getenv("LORA_DEV_EUI", "").lower()
LORA_FPORT = int(os.getenv("LORA_FPORT", "1"))
